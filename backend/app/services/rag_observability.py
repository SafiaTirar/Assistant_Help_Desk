from __future__ import annotations

import json
import logging
import math
import multiprocessing
import os
import signal
import select
import threading
import time
from collections import defaultdict
from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator

from app.services.rag_deadline import (
    QuestionTimeoutError,
    check_deadline,
    current_deadline,
    operation_timeout,
)


logger = logging.getLogger(__name__)
_current_trace: ContextVar["RagTrace | None"] = ContextVar("rag_trace", default=None)


@dataclass
class _CompletionResult:
    text: str
    raw: dict

    def __str__(self) -> str:
        return self.text


def _ollama_chat_worker(config: dict, prompt: str, connection) -> None:
    """Processus isolé : sa terminaison ferme réellement la socket Ollama."""
    client = None
    try:
        from ollama import Client

        client = Client(host=config["base_url"], timeout=config["http_timeout"])
        response = client.chat(
            model=config["model"],
            messages=[{"role": "user", "content": prompt}],
            stream=False,
            format="json" if config.get("json_mode") else "",
            options=config["options"],
            keep_alive=config.get("keep_alive"),
        )
        raw = dict(response)
        connection.send(("ok", raw))
    except BaseException as exc:
        connection.send(("error", type(exc).__name__, str(exc)))
    finally:
        close = getattr(client, "close", None)
        if close is not None:
            close()
        connection.close()


def _ollama_stop_worker(config: dict) -> None:
    """Demande à Ollama d'arrêter le runner après déconnexion forcée."""
    from ollama import Client

    client = Client(host=config["base_url"], timeout=5.0)
    try:
        client.generate(
            model=config["model"], prompt="", stream=False, keep_alive=0,
        )
    finally:
        close = getattr(client, "close", None)
        if close is not None:
            close()


def _stop_ollama_after_timeout(context, config: dict) -> None:
    cleanup = context.Process(target=_ollama_stop_worker, args=(config,))
    cleanup.start()
    cleanup.join(timeout=8)
    if cleanup.is_alive():
        cleanup.kill()
        cleanup.join(timeout=1)


def _is_ollama_llm(llm: Any) -> bool:
    return type(llm).__module__.startswith("llama_index.llms.ollama")


def _forked_ollama_payload(config: dict, prompt: str, write_fd: int) -> None:
    try:
        from ollama import Client

        client = Client(host=config["base_url"], timeout=config["http_timeout"])
        try:
            response = client.chat(
                model=config["model"],
                messages=[{"role": "user", "content": prompt}],
                stream=False,
                format="json" if config.get("json_mode") else "",
                options=config["options"],
                keep_alive=config.get("keep_alive"),
            )
            raw = dict(response)
            for key, value in list(raw.items()):
                if hasattr(value, "model_dump"):
                    raw[key] = value.model_dump()
            payload = {"status": "ok", "raw": raw}
        finally:
            close = getattr(client, "close", None)
            if close is not None:
                close()
    except BaseException as exc:
        payload = {
            "status": "error", "errorType": type(exc).__name__, "error": str(exc)
        }
    encoded = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    view = memoryview(encoded)
    while view:
        written = os.write(write_fd, view)
        view = view[written:]


def _wait_forked_pid(pid: int, timeout: float) -> bool:
    expires = time.monotonic() + timeout
    while time.monotonic() < expires:
        waited, _ = os.waitpid(pid, os.WNOHANG)
        if waited == pid:
            return True
        time.sleep(0.05)
    return False


def _reap_forked_pid_async(pid: int) -> None:
    """Récolte un enfant tardif sans bloquer le chemin de timeout utilisateur."""
    def reap() -> None:
        try:
            os.waitpid(pid, 0)
        except ChildProcessError:
            pass

    thread = threading.Thread(target=reap, daemon=True, name="ollama-child-reaper")
    thread.start()


def _terminate_and_reap_forked_pid_async(pid: int, timeout: float) -> None:
    """Borne un enfant de nettoyage sans retarder la réponse en timeout."""
    def terminate_and_reap() -> None:
        try:
            if not _wait_forked_pid(pid, timeout):
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    os.waitpid(pid, 0)
                except ChildProcessError:
                    pass
        except ChildProcessError:
            pass

    thread = threading.Thread(
        target=terminate_and_reap,
        daemon=True,
        name="ollama-cleanup-reaper",
    )
    thread.start()


def _stop_ollama_after_timeout_forked(config: dict) -> int:
    pid = os.fork()
    if pid == 0:
        try:
            _ollama_stop_worker(config)
        finally:
            os._exit(0)
    _terminate_and_reap_forked_pid_async(pid, 6.0)
    return pid


def _complete_ollama_with_posix_fork(llm, prompt: str, timeout: float, stage: str):
    options = dict(getattr(llm, "additional_kwargs", {}) or {})
    temperature = getattr(llm, "temperature", None)
    if temperature is not None:
        options.setdefault("temperature", temperature)
    context_window = getattr(llm, "context_window", None)
    if context_window not in (None, -1):
        options.setdefault("num_ctx", context_window)
    config = {
        "base_url": getattr(llm, "base_url"),
        "model": getattr(llm, "model"),
        "http_timeout": timeout,
        "json_mode": bool(getattr(llm, "json_mode", False)),
        "options": options,
        "keep_alive": getattr(llm, "keep_alive", None),
    }
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(read_fd)
        try:
            _forked_ollama_payload(config, prompt, write_fd)
        finally:
            os.close(write_fd)
            os._exit(0)
    os.close(write_fd)
    expires = time.monotonic() + timeout
    chunks = []
    try:
        while True:
            remaining = expires - time.monotonic()
            if remaining <= 0:
                raise QuestionTimeoutError(
                    stage,
                    current_deadline().elapsed() if current_deadline() else timeout,
                    current_deadline().timeout_seconds if current_deadline() else timeout,
                )
            ready, _, _ = select.select([read_fd], [], [], min(0.25, remaining))
            if not ready:
                continue
            chunk = os.read(read_fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        os.waitpid(pid, 0)
        payload = json.loads(b"".join(chunks).decode("utf-8"))
        if payload.get("status") != "ok":
            raise RuntimeError(
                f"{payload.get('errorType', 'OllamaError')}: {payload.get('error', '')}"
            )
        raw = payload["raw"]
        return _CompletionResult(raw.get("message", {}).get("content", ""), raw)
    except QuestionTimeoutError:
        record_trace_event("cancellation_requested", stage=stage, childPid=pid)
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        reaped = _wait_forked_pid(pid, 0.5)
        if not reaped:
            _reap_forked_pid_async(pid)
        cleanup_pid = _stop_ollama_after_timeout_forked(config)
        record_trace_event(
            "cancellation_completed",
            stage=stage,
            childPid=pid,
            childReaped=reaped,
            cleanupPid=cleanup_pid,
            cleanupMode="asynchronous_bounded",
        )
        raise
    finally:
        os.close(read_fd)


def _complete_ollama_with_hard_timeout(llm, prompt: str, timeout: float, stage: str):
    if hasattr(os, "fork"):
        return _complete_ollama_with_posix_fork(llm, prompt, timeout, stage)
    options = dict(getattr(llm, "additional_kwargs", {}) or {})
    temperature = getattr(llm, "temperature", None)
    if temperature is not None:
        options.setdefault("temperature", temperature)
    context_window = getattr(llm, "context_window", None)
    if context_window not in (None, -1):
        options.setdefault("num_ctx", context_window)
    config = {
        "base_url": getattr(llm, "base_url"),
        "model": getattr(llm, "model"),
        "http_timeout": timeout,
        "json_mode": bool(getattr(llm, "json_mode", False)),
        "options": options,
        "keep_alive": getattr(llm, "keep_alive", None),
    }
    # Dans le conteneur Linux, ``spawn`` attend le bootstrap Python de l'enfant
    # avant de rendre la main. Sous saturation Ollama, cette phase a déjà duré
    # plusieurs minutes et se situe avant toute boucle de deadline. ``fork``
    # rend immédiatement le contrôle au parent. Le fallback conserve la
    # compatibilité des plates-formes sans fork.
    start_method = (
        "fork" if "fork" in multiprocessing.get_all_start_methods() else "spawn"
    )
    context = multiprocessing.get_context(start_method)
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=_ollama_chat_worker, args=(config, prompt, child))
    process.start()
    child.close()
    timed_out = threading.Event()

    def kill_at_deadline() -> None:
        timed_out.set()
        if process.pid and process.is_alive():
            # SIGKILL est intentionnel : le processus ne possède aucun état métier,
            # uniquement la socket HTTP. Sa mort ferme le flux même si httpx est
            # bloqué dans une lecture que SIGTERM ne réveille pas.
            os.kill(process.pid, signal.SIGKILL)

    watchdog = threading.Timer(timeout, kill_at_deadline)
    watchdog.daemon = True
    watchdog.start()
    try:
        # Ne jamais bloquer dans un unique poll(timeout) : sur certaines plates-
        # formes, le syscall est automatiquement redémarré après SIGALRM et le
        # handler Python n'est exécuté qu'à son retour. Cette boucle rend la main
        # à l'interpréteur au moins quatre fois par seconde.
        wait_expires = time.monotonic() + timeout
        ready = False
        while not ready and not timed_out.is_set():
            remaining = wait_expires - time.monotonic()
            if remaining <= 0:
                timed_out.set()
                break
            ready = parent.poll(min(0.25, remaining))
        if not ready or timed_out.is_set():
            if process.is_alive():
                process.kill()
            process.join(timeout=2)
            deadline = current_deadline()
            if deadline is not None:
                raise QuestionTimeoutError(
                    stage, deadline.elapsed(), deadline.timeout_seconds
                )
            _stop_ollama_after_timeout(context, config)
            raise TimeoutError(f"appel Ollama interrompu après {timeout:.3f}s")
        try:
            payload = parent.recv()
        except EOFError:
            if timed_out.is_set():
                deadline = current_deadline()
                if deadline is not None:
                    raise QuestionTimeoutError(
                        stage, deadline.elapsed(), deadline.timeout_seconds
                    )
                raise TimeoutError(f"appel Ollama interrompu après {timeout:.3f}s")
            raise RuntimeError("Le processus Ollama s'est arrêté sans réponse.")
        process.join(timeout=2)
        if payload[0] == "error":
            error_type, message = payload[1], payload[2]
            raise RuntimeError(f"{error_type}: {message}")
        raw = payload[1]
        return _CompletionResult(raw.get("message", {}).get("content", ""), raw)
    except QuestionTimeoutError:
        if process.is_alive():
            process.kill()
            process.join(timeout=1)
        _stop_ollama_after_timeout(context, config)
        raise
    finally:
        watchdog.cancel()
        parent.close()
        if process.is_alive():
            process.terminate()
            process.join(timeout=2)


def _milliseconds(value: Any) -> float | None:
    """Ollama exprime ses durées natives en nanosecondes."""
    if value is None:
        return None
    try:
        return round(float(value) / 1_000_000, 3)
    except (TypeError, ValueError):
        return None


def _raw_mapping(response: Any) -> dict:
    raw = getattr(response, "raw", None)
    if isinstance(raw, Mapping):
        return dict(raw)
    if hasattr(raw, "model_dump"):
        dumped = raw.model_dump()
        return dumped if isinstance(dumped, dict) else {}
    return {}


def _safe_number(value: Any, cast=float):
    try:
        return cast(value) if value is not None else None
    except (TypeError, ValueError):
        return None


@dataclass
class RagTrace:
    question_id: str | None
    question: str
    started_ns: int = field(default_factory=time.perf_counter_ns)
    steps_ms: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    step_events: list[dict] = field(default_factory=list)
    lifecycle_events: list[dict] = field(default_factory=list)
    llm_calls: list[dict] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    finished_ns: int | None = None

    def add_step(self, name: str, elapsed_ms: float, **details: Any) -> None:
        elapsed_ms = round(elapsed_ms, 3)
        self.steps_ms[name] += elapsed_ms
        event = {"step": name, "elapsedMs": elapsed_ms}
        event.update({key: value for key, value in details.items() if value is not None})
        self.step_events.append(event)

    def set_attribute(self, name: str, value: Any) -> None:
        self.attributes[name] = value

    def add_lifecycle_event(self, name: str, **details: Any) -> None:
        event = {
            "event": name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "elapsedMs": round(
                (time.perf_counter_ns() - self.started_ns) / 1_000_000, 3
            ),
            "caseId": self.question_id,
        }
        event.update({key: value for key, value in details.items() if value is not None})
        self.lifecycle_events.append(event)

    def finish(self) -> None:
        if self.finished_ns is None:
            self.finished_ns = time.perf_counter_ns()

    def to_dict(self) -> dict:
        self.finish()
        total_ms = (self.finished_ns - self.started_ns) / 1_000_000
        return {
            "questionId": self.question_id,
            "question": self.question,
            "totalMs": round(total_ms, 3),
            "stepsMs": {key: round(value, 3) for key, value in self.steps_ms.items()},
            "stepEvents": list(self.step_events),
            "lifecycleEvents": list(self.lifecycle_events),
            "llmCallCount": len(self.llm_calls),
            "llmCalls": list(self.llm_calls),
            "attributes": dict(self.attributes),
        }


def current_trace() -> RagTrace | None:
    return _current_trace.get()


@contextmanager
def trace_question(question_id: str | None, question: str) -> Iterator[RagTrace]:
    trace = RagTrace(question_id=question_id, question=question)
    token = _current_trace.set(trace)
    trace.add_lifecycle_event("request_start")
    outcome = "normal"
    try:
        yield trace
    except QuestionTimeoutError as exc:
        outcome = "timeout"
        trace.add_lifecycle_event(
            "timeout_triggered",
            stage=exc.stage,
            timeoutSeconds=exc.timeout_seconds,
        )
        raise
    except Exception:
        outcome = "error"
        raise
    finally:
        trace.add_lifecycle_event("response_end", outcome=outcome)
        trace.finish()
        _current_trace.reset(token)
        logger.info("rag_trace %s", json.dumps(trace.to_dict(), ensure_ascii=False, default=str))


@contextmanager
def timed_step(name: str, **details: Any) -> Iterator[None]:
    started = time.perf_counter_ns()
    trace = current_trace()
    previous_step = trace.attributes.get("activeStep") if trace is not None else None
    if trace is not None:
        trace.set_attribute("activeStep", name)
    check_deadline(name)
    try:
        yield
    finally:
        trace = current_trace()
        if trace is not None:
            trace.add_step(name, (time.perf_counter_ns() - started) / 1_000_000, **details)
            lifecycle_name = {
                "classification": "classification_end",
                "query_embedding": "embedding_end",
                "classification_example_embedding": "embedding_end",
                "classification_query_embedding": "embedding_end",
                "semantic_embedding": "embedding_end",
                "qdrant_search": "qdrant_end",
                "reranking": "reranking_end",
                "pre_generation_validation": "validation_end",
                "anti_hallucination_validation": "validation_end",
                "evaluation_validation": "validation_end",
            }.get(name)
            if lifecycle_name is not None:
                trace.add_lifecycle_event(lifecycle_name, step=name, **details)
            trace.set_attribute("activeStep", previous_step)
        check_deadline(name)


def set_trace_attribute(name: str, value: Any) -> None:
    trace = current_trace()
    if trace is not None:
        trace.set_attribute(name, value)


def record_trace_event(name: str, **details: Any) -> None:
    trace = current_trace()
    if trace is not None:
        trace.add_lifecycle_event(name, **details)


def complete_with_metrics(llm, prompt: str, call_name: str):
    """Exécute exactement un appel LLM et conserve les métriques Ollama réelles."""
    started = time.perf_counter_ns()
    response = None
    error = None
    configured_timeout = float(getattr(llm, "request_timeout", 30.0) or 30.0)
    effective_timeout = operation_timeout(configured_timeout, call_name)
    effective_llm = llm
    record_trace_event(
        "ollama_request_start",
        callName=call_name,
        configuredTimeoutSeconds=configured_timeout,
        effectiveTimeoutSeconds=effective_timeout,
    )
    set_trace_attribute("ollamaFirstTokenObservable", False)
    if effective_timeout < configured_timeout:
        copier = getattr(type(llm), "model_copy", None) or getattr(type(llm), "copy", None)
        if copier is not None:
            effective_llm = copier(llm, update={"request_timeout": effective_timeout})
            # Le client Ollama/httpx est paresseux. Un clone ne doit pas réutiliser
            # le client de l'instance originale, construit avec un timeout plus long.
            for attribute in ("_client", "_async_client"):
                if hasattr(effective_llm, attribute):
                    setattr(effective_llm, attribute, None)
    try:
        if _is_ollama_llm(effective_llm):
            response = _complete_ollama_with_hard_timeout(
                effective_llm, prompt, effective_timeout, call_name
            )
        else:
            response = effective_llm.complete(prompt)
        check_deadline(call_name)
        return response
    except Exception as exc:
        error = exc
        raise
    finally:
        elapsed_ms = round((time.perf_counter_ns() - started) / 1_000_000, 3)
        record_trace_event(
            "ollama_request_end",
            callName=call_name,
            outcome="error" if error is not None else "normal",
            errorType=type(error).__name__ if error is not None else None,
        )
        raw = _raw_mapping(response) if response is not None else {}
        eval_count = _safe_number(raw.get("eval_count"), int)
        eval_duration_ns = _safe_number(raw.get("eval_duration"), float)
        tokens_per_second = None
        if eval_count is not None and eval_duration_ns is not None and eval_duration_ns > 0:
            tokens_per_second = round(eval_count / (eval_duration_ns / 1_000_000_000), 3)
        model = getattr(effective_llm, "model", None)
        additional_kwargs = getattr(effective_llm, "additional_kwargs", {}) or {}
        record = {
            "llmCall": call_name,
            "attempt": 1,
            "retryCount": 0,
            "model": model,
            "clientElapsedMs": elapsed_ms,
            "totalMs": _milliseconds(raw.get("total_duration")),
            "loadMs": _milliseconds(raw.get("load_duration")),
            "promptEvalMs": _milliseconds(raw.get("prompt_eval_duration")),
            "generationMs": _milliseconds(raw.get("eval_duration")),
            "promptTokens": _safe_number(raw.get("prompt_eval_count"), int),
            "outputTokens": eval_count,
            "tokensPerSecond": tokens_per_second,
            "promptChars": len(prompt),
            "numCtx": additional_kwargs.get("num_ctx", getattr(llm, "context_window", None)),
            "numPredict": additional_kwargs.get("num_predict"),
            "keepAlive": getattr(effective_llm, "keep_alive", None),
            "requestTimeoutSeconds": effective_timeout,
            "doneReason": raw.get("done_reason"),
            "errorType": type(error).__name__ if error is not None else None,
            "error": str(error) if error is not None else None,
            "timeout": bool(error and "timeout" in type(error).__name__.lower()),
            "metricsAvailable": bool(raw),
        }
        trace = current_trace()
        if trace is not None:
            trace.llm_calls.append(record)
            trace.add_step(call_name, elapsed_ms, llmCallIndex=len(trace.llm_calls))
        logger.info("ollama_call %s", json.dumps({
            "questionId": trace.question_id if trace else None,
            **record,
        }, ensure_ascii=False, default=str))
        if effective_llm is not llm:
            client = getattr(effective_llm, "_client", None)
            close = getattr(client, "close", None)
            if close is not None:
                close()


def record_embedding_call(
    *,
    call_name: str,
    model: str,
    item_count: int,
    elapsed_ms: float,
    cached_items: int = 0,
    error: Exception | None = None,
) -> None:
    trace = current_trace()
    event = {
        "embeddingCall": call_name,
        "model": model,
        "itemCount": item_count,
        "cachedItems": cached_items,
        "elapsedMs": round(elapsed_ms, 3),
        "errorType": type(error).__name__ if error is not None else None,
    }
    if trace is not None:
        calls = list(trace.attributes.get("embeddingCalls") or [])
        calls.append(event)
        trace.set_attribute("embeddingCalls", calls)
        trace.set_attribute("embeddingCallCount", len(calls))
        trace.set_attribute(
            "embeddingItemCount",
            sum(int(item.get("itemCount") or 0) for item in calls),
        )
        trace.set_attribute(
            "embeddingTotalMs",
            round(sum(float(item.get("elapsedMs") or 0.0) for item in calls), 3),
        )
    logger.info("ollama_embedding %s", json.dumps({
        "questionId": trace.question_id if trace else None,
        **event,
    }, ensure_ascii=False, default=str))


def nearest_rank_percentile(values: list[int | float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]
