from __future__ import annotations

import time
import signal
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator


class QuestionTimeoutError(TimeoutError):
    """La deadline globale d'une question a été atteinte."""

    def __init__(self, stage: str, elapsed_seconds: float, timeout_seconds: float) -> None:
        self.stage = stage
        self.elapsed_seconds = elapsed_seconds
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"deadline de {timeout_seconds:g}s dépassée pendant l'étape {stage} "
            f"(écoulé: {elapsed_seconds:.3f}s)"
        )


@dataclass(frozen=True)
class QuestionDeadline:
    started: float
    expires: float
    timeout_seconds: float

    def elapsed(self) -> float:
        return max(0.0, time.perf_counter() - self.started)

    def remaining(self, stage: str) -> float:
        remaining = self.expires - time.perf_counter()
        if remaining <= 0:
            raise QuestionTimeoutError(stage, self.elapsed(), self.timeout_seconds)
        return remaining


_current_deadline: ContextVar[QuestionDeadline | None] = ContextVar(
    "rag_question_deadline", default=None
)


@contextmanager
def question_deadline(timeout_seconds: float) -> Iterator[QuestionDeadline]:
    if timeout_seconds <= 0:
        raise ValueError("La deadline d'une question doit être strictement positive.")
    started = time.perf_counter()
    deadline = QuestionDeadline(started, started + timeout_seconds, timeout_seconds)
    token = _current_deadline.set(deadline)
    use_signal = (
        threading.current_thread() is threading.main_thread()
        and hasattr(signal, "setitimer")
        and hasattr(signal, "ITIMER_REAL")
    )
    previous_handler = None
    previous_timer = None
    if use_signal:
        previous_handler = signal.getsignal(signal.SIGALRM)
        previous_timer = signal.getitimer(signal.ITIMER_REAL)

        def deadline_alarm(_signum, _frame) -> None:
            raise QuestionTimeoutError(
                "global_deadline", deadline.elapsed(), deadline.timeout_seconds
            )

        signal.signal(signal.SIGALRM, deadline_alarm)
        signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
    try:
        yield deadline
        deadline.remaining("pipeline_completion")
    finally:
        if use_signal:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)
            if previous_timer and previous_timer[0] > 0:
                signal.setitimer(signal.ITIMER_REAL, *previous_timer)
        _current_deadline.reset(token)


def current_deadline() -> QuestionDeadline | None:
    return _current_deadline.get()


def check_deadline(stage: str) -> None:
    deadline = current_deadline()
    if deadline is not None:
        deadline.remaining(stage)


def operation_timeout(configured_timeout: float, stage: str, minimum: float = 0.001) -> float:
    """Borne un timeout I/O par le temps restant de la question."""
    deadline = current_deadline()
    if deadline is None:
        return configured_timeout
    return max(minimum, min(configured_timeout, deadline.remaining(stage)))
