"""Exécute manuellement un jeu d'évaluation RAG, sans écrire en base."""

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.rag_service import get_rag_service
from app.services.conversation_memory_service import contextualize_question
from app.services.evaluation_service import (
    _evaluate_checks,
    _node_record,
    _percentile,
    _retrieval_metrics,
)
from app.services.rag_deadline import QuestionTimeoutError, question_deadline
from app.services.rag_observability import record_trace_event, set_trace_attribute, trace_question


DEFAULT_CASES = Path(__file__).with_name("rag_quality_example_cases.json")


def normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in value if not unicodedata.combining(char))


def keywords(text: str) -> set[str]:
    stop_words = {
        "a", "au", "aux", "ce", "ces", "cette", "de", "des", "du", "et",
        "il", "la", "le", "les", "ou", "par", "pour", "que", "qui", "un", "une",
    }
    return {
        word
        for word in re.findall(r"[a-z0-9]+", normalize(text))
        if len(word) > 2 and word not in stop_words
    }


def temporal_markers(text: str) -> set[str]:
    """Extrait les jalons qui peuvent constituer seuls une réponse exacte."""
    normalized = normalize(text)
    return {
        re.sub(r"\s+", "", marker)
        for marker in re.findall(
            r"\b(?:[ndj]\s*[-+]\s*\d+|\d+\s*(?:jour|jours|semaine|semaines|mois))\b",
            normalized,
        )
    }
def expected_status(case: dict) -> str:
    return case.get("expectedStatus") or case.get("expected_status") or case["statut_attendu"]


def evaluation_reference(case: dict) -> SimpleNamespace:
    """Adapte les formats JSON historiques au référentiel de l'évaluateur partagé."""
    return SimpleNamespace(
        question=case["question"],
        expected_status=expected_status(case),
        expected_answer=case.get(
            "expectedAnswer",
            case.get("expected_answer", case.get("reponse_reference", "")),
        ),
        expected_pages=case.get(
            "expectedPages",
            case.get("expected_pages", case.get("pages_attendues", [])),
        ),
        expected_sections=case.get(
            "expectedSections",
            case.get("expected_sections", case.get("sections_attendues", [])),
        ),
        expected_documents=case.get(
            "expectedDocuments",
            case.get("expected_documents", case.get("documents_attendus", [])),
        ),
        required_terms=case.get(
            "requiredTerms",
            case.get("required_terms", case.get("termes_requis", [])),
        ),
    )


def evaluate_case_checks(case: dict, result) -> tuple[dict, list[str], float | None]:
    """Applique exactement le verdict utilisé par la campagne administrative."""
    return _evaluate_checks(evaluation_reference(case), result)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument(
        "--additional-cases", type=Path, action="append", default=[],
        help="Ajoute un ou plusieurs jeux sans modifier le fichier historique.",
    )
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--case-code", action="append", default=[],
        help="Ne conserve que les codes indiqués (option répétable).",
    )
    parser.add_argument("--candidate-pool", type=int)
    parser.add_argument(
        "--question-timeout",
        type=float,
        default=float(os.getenv("RAG_QUESTION_TIMEOUT_SECONDS", "180")),
    )
    parser.add_argument("--include-diagnostics", action="store_true")
    parser.add_argument(
        "--compact-timeout-diagnostics", action="store_true",
        help="Omet les détails de ranking volumineux dans la sortie des timeouts.",
    )
    args = parser.parse_args()

    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    for additional_path in args.additional_cases:
        cases.extend(json.loads(additional_path.read_text(encoding="utf-8")))
    if args.case_code:
        selected_codes = set(args.case_code)
        cases = [case for case in cases if case.get("code", case.get("id")) in selected_codes]
    cases = cases[max(args.start - 1, 0):]
    if args.limit is not None:
        cases = cases[:args.limit]

    service = get_rag_service()
    if args.candidate_pool is not None:
        if args.candidate_pool < 1:
            parser.error("--candidate-pool doit être strictement positif")
        service.candidate_pool_size = args.candidate_pool
    passed = 0
    latencies = []
    retrieval_latencies = []
    retrieval_results = []
    timeout_count = 0
    technical_error_count = 0
    embedding_calls = []
    retrieval_step_samples = defaultdict(list)
    category_totals = defaultdict(int)
    category_passed = defaultdict(int)
    false_positive_out_of_scope = 0
    false_negative_out_of_scope = 0
    started = time.perf_counter()
    for index, case in enumerate(cases, start=1):
        case_started = time.perf_counter()
        wanted_status = expected_status(case)
        reference = evaluation_reference(case)
        category = case.get("category", "non_classee")
        category_totals[category] += 1
        try:
            with trace_question(case.get("code", case.get("id", str(index))), case["question"]) as trace:
                with question_deadline(args.question_timeout):
                    set_trace_attribute("deadlineConfiguredSeconds", args.question_timeout)
                    set_trace_attribute("candidatePoolSize", service.candidate_pool_size)
                    history = [SimpleNamespace(**message) for message in case.get("history", [])]
                    retrieval_question = contextualize_question(
                        case["question"], history, service.llm,
                    )
                    record_trace_event(
                        "memory_end", contextualized=retrieval_question != case["question"]
                    )
                    result = service.answer_question(retrieval_question)
                    retrieval_latency = result.retrieval_latency_ms
                    if retrieval_latency is not None:
                        retrieval_latencies.append(retrieval_latency)
                    retrieval = _retrieval_metrics(
                        reference,
                        [_node_record(node) for node in result.retrieved_nodes[:5]],
                    )
                    if retrieval["recall5"] is not None:
                        retrieval_results.append(retrieval)
            diagnostics = trace.to_dict()
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - case_started) * 1000)
            latencies.append(elapsed_ms)
            is_timeout = isinstance(exc, QuestionTimeoutError) or "timeout" in type(exc).__name__.lower()
            timeout_count += int(is_timeout)
            technical_error_count += int(not is_timeout)
            diagnostics = trace.to_dict() if "trace" in locals() else {}
            embedding_calls.extend(
                (diagnostics.get("attributes") or {}).get("embeddingCalls") or []
            )
            for name, duration in (diagnostics.get("stepsMs") or {}).items():
                retrieval_step_samples[name].append(duration)
            printed_diagnostics = diagnostics
            if args.compact_timeout_diagnostics:
                compact_attributes = dict(diagnostics.get("attributes") or {})
                compact_attributes.pop("retrievalDiagnostics", None)
                printed_diagnostics = {
                    **diagnostics,
                    "stepEvents": [],
                    "attributes": compact_attributes,
                }
            print(json.dumps({
                "case": case.get("code", case.get("id", index)),
                "success": False,
                "question": case["question"],
                "expected_status": wanted_status,
                "actual_status": "TIMEOUT" if is_timeout else None,
                "error": f"{type(exc).__name__}: {exc}",
                "deadline_configured_seconds": args.question_timeout,
                "active_step": (
                    exc.stage if isinstance(exc, QuestionTimeoutError)
                    else (diagnostics.get("attributes") or {}).get("activeStep")
                ),
                "llm_call_count": diagnostics.get("llmCallCount", 0),
                "retrieval_time_ms": (diagnostics.get("stepsMs") or {}).get("retrieval"),
                "ollama_time_ms": sum(
                    float(item.get("clientElapsedMs") or 0)
                    for item in diagnostics.get("llmCalls", [])
                ),
                "latency_seconds": round(time.perf_counter() - case_started, 2),
                "diagnostics": printed_diagnostics,
            }, ensure_ascii=False), flush=True)
            continue

        embedding_calls.extend(
            (diagnostics.get("attributes") or {}).get("embeddingCalls") or []
        )
        for name, duration in (diagnostics.get("stepsMs") or {}).items():
            retrieval_step_samples[name].append(duration)

        checks, failure_reasons, reference_recall = evaluate_case_checks(case, result)
        success = all(checks.values())
        passed += int(success)
        category_passed[category] += int(success)
        false_positive_out_of_scope += int(
            result.status == "hors_perimetre" and wanted_status != "hors_perimetre"
        )
        false_negative_out_of_scope += int(
            result.status != "hors_perimetre" and wanted_status == "hors_perimetre"
        )
        expected_pages = set(case.get("expectedPages", case.get("pages_attendues", [])))
        actual_pages = {
            page for source in result.sources for page in source.pages
        }

        output_record = {
            "case": case.get("code", case.get("id", index)),
            "success": success,
            "question": case["question"],
            "retrieval_question": retrieval_question,
            "expected_status": wanted_status,
            "actual_status": result.status,
            "confidence": round(result.confidence_score, 4),
            "checks": checks,
            "failure_reasons": failure_reasons,
            "required_terms_found": checks["requiredTermsMatch"],
            "reference_answer_supported": checks["answerReferenceMatch"],
            "reference_keyword_recall": (
                round(reference_recall, 3) if reference_recall is not None else None
            ),
            "answer_preview": result.answer[:300],
            "expected_pages": sorted(expected_pages),
            "actual_pages": sorted(actual_pages),
            "expected_page_found": checks["pageMatch"] if expected_pages else None,
            "retrieval_rank": retrieval["rank"],
            "recall_at_1": retrieval["recall1"],
            "recall_at_3": retrieval["recall3"],
            "recall_at_5": retrieval["recall5"],
            "reciprocal_rank": retrieval["reciprocalRank"],
            "retrieval_latency_ms": retrieval_latency,
            "latency_seconds": round(time.perf_counter() - case_started, 2),
            "embedding_call_count": len(
                (diagnostics.get("attributes") or {}).get("embeddingCalls") or []
            ),
            "embedding_items_per_call": [
                item.get("itemCount") for item in
                ((diagnostics.get("attributes") or {}).get("embeddingCalls") or [])
            ],
            "retrieval_steps_ms": {
                name: duration for name, duration in (diagnostics.get("stepsMs") or {}).items()
                if name in {
                    "query_embedding", "qdrant_search", "candidate_preparation",
                    "semantic_embedding", "semantic_similarity", "lexical_score",
                    "intent_score", "final_reranking",
                }
            },
            "generation": (diagnostics.get("llmCalls") or [None])[-1],
        }
        if args.include_diagnostics:
            retrieval_diagnostics = (
                (diagnostics.get("attributes") or {}).get("retrievalDiagnostics") or {}
            )
            output_record["top_15_candidates"] = (
                retrieval_diagnostics.get("ranked_candidates") or []
            )[:15]
            output_record["top_5_final"] = (
                retrieval_diagnostics.get("selected_chunks") or []
            )[:5]
        print(json.dumps(output_record, ensure_ascii=False), flush=True)
        latencies.append(round((time.perf_counter() - case_started) * 1000))

    embedding_durations = [
        float(item.get("elapsedMs") or 0.0) for item in embedding_calls
    ]
    retrieval_evaluable_cases = len(retrieval_results)
    recall1_hits = sum(item["recall1"] for item in retrieval_results)
    recall3_hits = sum(item["recall3"] for item in retrieval_results)
    recall5_hits = sum(item["recall5"] for item in retrieval_results)
    print(json.dumps({
        "passed": passed,
        "total": len(cases),
        "score_percent": round(passed / max(len(cases), 1) * 100),
        "duration_seconds": round(time.perf_counter() - started, 2),
        "candidate_pool": service.candidate_pool_size,
        "final_top_k": service.final_top_k,
        "timeout_count": timeout_count,
        "technical_error_count": technical_error_count,
        "category_results": {
            category: {
                "passed": category_passed[category],
                "total": total,
                "score_percent": round(category_passed[category] / total * 100),
            }
            for category, total in sorted(category_totals.items())
        },
        "false_positive_hors_perimetre": false_positive_out_of_scope,
        "false_negative_hors_perimetre": false_negative_out_of_scope,
        "embedding_call_count": len(embedding_calls),
        "embedding_total_duration_ms": round(sum(embedding_durations), 3),
        "embedding_p50_ms": _percentile(embedding_durations, 0.50),
        "embedding_p95_ms": _percentile(embedding_durations, 0.95),
        "embedding_max_ms": max(embedding_durations) if embedding_durations else None,
        "items_per_embedding_call": [item.get("itemCount") for item in embedding_calls],
        "retrieval_steps_p50_ms": {
            name: _percentile(values, 0.50)
            for name, values in retrieval_step_samples.items()
            if name in {
                "query_embedding", "qdrant_search", "candidate_preparation",
                "semantic_embedding", "semantic_similarity", "lexical_score",
                "intent_score", "final_reranking",
            }
        },
        "retrieval_steps_p95_ms": {
            name: _percentile(values, 0.95)
            for name, values in retrieval_step_samples.items()
            if name in {
                "query_embedding", "qdrant_search", "candidate_preparation",
                "semantic_embedding", "semantic_similarity", "lexical_score",
                "intent_score", "final_reranking",
            }
        },
        "retrieval_evaluable_cases": retrieval_evaluable_cases,
        "recall_at_1_hits": recall1_hits,
        "recall_at_3_hits": recall3_hits,
        "recall_at_5_hits": recall5_hits,
        "recall_at_1": round(recall1_hits / retrieval_evaluable_cases, 4) if retrieval_results else None,
        "recall_at_3": round(recall3_hits / retrieval_evaluable_cases, 4) if retrieval_results else None,
        "recall_at_5": round(recall5_hits / retrieval_evaluable_cases, 4) if retrieval_results else None,
        "mrr": round(sum(item["reciprocalRank"] for item in retrieval_results) / len(retrieval_results), 4) if retrieval_results else None,
        "latency_p50_ms": _percentile(latencies, 0.50),
        "latency_p95_ms": _percentile(latencies, 0.95),
        "retrieval_latency_p50_ms": _percentile(retrieval_latencies, 0.50),
        "retrieval_latency_p95_ms": _percentile(retrieval_latencies, 0.95),
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
