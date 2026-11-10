import math
import os
import re
import time
import unicodedata
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.evaluation import EvaluationQuestion, EvaluationResult, EvaluationRun
from app.services.conversation_memory_service import contextualize_question
from app.services.rag_observability import (
    record_trace_event,
    set_trace_attribute,
    timed_step,
    trace_question,
)
from app.services.rag_deadline import QuestionTimeoutError, question_deadline
from app.services.rag_service import RagService, get_rag_service


REFERENCE_RECALL_THRESHOLD = 0.20
DATASET_SPLITS = {"calibration", "validation", "all"}
RAG_QUESTION_TIMEOUT_SECONDS = float(os.getenv("RAG_QUESTION_TIMEOUT_SECONDS", "180"))
RAG_EVALUATION_CONCURRENCY = int(os.getenv("RAG_EVALUATION_CONCURRENCY", "1"))


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(char for char in value if not unicodedata.combining(char))


def _keywords(text: str) -> set[str]:
    stop_words = {
        "a", "au", "aux", "ce", "ces", "cette", "de", "des", "du", "et",
        "il", "la", "le", "les", "ou", "par", "pour", "que", "qui", "un", "une",
    }
    return {
        word for word in re.findall(r"[a-z0-9]+", _normalize(text))
        if len(word) > 2 and word not in stop_words
    }


def _reference_recall(expected: str, actual: str) -> float | None:
    expected_words = _keywords(expected)
    if not expected_words:
        return None
    return len(expected_words & _keywords(actual)) / len(expected_words)


def _percentile(values: list[int | float], percentile: float) -> int | float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def _serialize_sources(sources: list) -> list[dict]:
    return [
        {
            "documentTitle": source.document_title,
            "fileName": source.file_name,
            "pages": source.pages,
            "section": source.section,
            "excerpt": source.excerpt,
            "chunkId": source.chunk_id,
        }
        for source in sources
    ]


def _node_record(node) -> dict:
    metadata = node.metadata or {}
    scores = metadata.get("_rag_scores") or {}
    page = metadata.get("page") or metadata.get("page_label")
    try:
        page = int(page) if page is not None else None
    except (TypeError, ValueError):
        page = None
    return {
        "chunkId": metadata.get("chunk_id") or getattr(node, "node_id", None),
        "documentId": metadata.get("app_document_id"),
        "documentTitle": metadata.get("document_title"),
        "fileName": metadata.get("file_name"),
        "page": page,
        "section": metadata.get("section"),
        "documentVersionId": metadata.get("document_version_id"),
        "indexGeneration": metadata.get("index_generation"),
        "documentActive": (
            True if metadata.get("_qdrant_active_filter_matched")
            else metadata.get("active")
        ),
        "embeddedDocumentActive": metadata.get("active"),
        "activeFilterMatched": bool(metadata.get("_qdrant_active_filter_matched")),
        "vectorScore": scores.get("vector_score", float(node.score or 0.0)),
        "semanticScore": scores.get("semantic_score"),
        "lexicalScore": scores.get("lexical_score"),
        "intentScore": scores.get("intent_score"),
        "finalScore": scores.get("final_score", float(node.score or 0.0)),
    }


def _document_aliases(record: dict) -> set[str]:
    return {
        _normalize(str(value))
        for value in (
            record.get("documentId"), record.get("documentTitle"), record.get("fileName")
        )
        if value
    }


def _matches_expected_document(record: dict, expected_documents: list[str]) -> bool:
    if not expected_documents:
        return True
    aliases = _document_aliases(record)
    return any(_normalize(reference) in aliases for reference in expected_documents)


def _relevant_rank(question: EvaluationQuestion, records: list[dict]) -> int | None:
    expected_pages = {int(page) for page in (question.expected_pages or [])}
    expected_sections = {_normalize(section) for section in (question.expected_sections or [])}
    for rank, record in enumerate(records, start=1):
        if not _matches_expected_document(record, question.expected_documents or []):
            continue
        location_expected = bool(expected_pages or expected_sections)
        page_match = record.get("page") in expected_pages if expected_pages else False
        section_match = (
            _normalize(record.get("section")) in expected_sections
            if expected_sections else False
        )
        if not location_expected or page_match or section_match:
            return rank
    return None


def _retrieval_metrics(question: EvaluationQuestion, records: list[dict]) -> dict:
    if question.expected_status != "reponse_trouvee":
        return {
            "rank": None, "recall1": None, "recall3": None,
            "recall5": None, "reciprocalRank": None,
        }
    rank = _relevant_rank(question, records)
    return {
        "rank": rank,
        "recall1": rank is not None and rank <= 1,
        "recall3": rank is not None and rank <= 3,
        "recall5": rank is not None and rank <= 5,
        "reciprocalRank": 1.0 / rank if rank else 0.0,
    }


def _evaluate_checks(question: EvaluationQuestion, result) -> tuple[dict, list[str], float | None]:
    actual_answer = result.answer or ""
    expected_pages = {int(page) for page in question.expected_pages}
    actual_pages = {int(page) for source in result.sources for page in source.pages}
    expected_sections = {_normalize(section) for section in question.expected_sections if section}
    actual_sections = {_normalize(source.section) for source in result.sources if source.section}
    reference_recall = _reference_recall(question.expected_answer, actual_answer)
    status_match = result.status == question.expected_status
    required_terms_match = all(
        _normalize(term) in _normalize(actual_answer) for term in question.required_terms
    )
    answer_reference_match = not (
        question.expected_status == "reponse_trouvee"
        and reference_recall is not None
        and reference_recall < REFERENCE_RECALL_THRESHOLD
    )
    source_present = bool(result.sources) if question.expected_status == "reponse_trouvee" else True
    location_applicable = question.expected_status == "reponse_trouvee"
    page_match = (
        bool(expected_pages & actual_pages)
        if location_applicable and expected_pages else True
    )
    section_match = (
        bool(expected_sections & actual_sections)
        if location_applicable and expected_sections else True
    )
    document_match = (
        any(
            _matches_expected_document(
                {"documentTitle": source.document_title, "fileName": source.file_name},
                question.expected_documents or [],
            )
            for source in result.sources
        )
        if location_applicable and question.expected_documents else True
    )

    if result.status == "reponse_trouvee":
        context = "\n".join(result.evidence or [source.excerpt for source in result.sources])
        grounded = bool(context) and not (
            RagService._has_unsupported_factual_numbers(actual_answer, context, question.question)
            or RagService._has_unsupported_named_entities(actual_answer, context, question.question)
            or RagService._has_unsupported_sentence_claims(actual_answer, context, question.question)
        )
    else:
        grounded = True

    checks = {
        "statusMatch": status_match,
        "requiredTermsMatch": required_terms_match,
        "answerReferenceMatch": answer_reference_match,
        "sourcePresent": source_present,
        "documentMatch": document_match,
        "pageMatch": page_match,
        "sectionMatch": section_match,
        "grounded": grounded,
    }
    reason_labels = {
        "statusMatch": "Statut obtenu différent du statut attendu.",
        "requiredTermsMatch": "Un ou plusieurs termes requis sont absents.",
        "answerReferenceMatch": "La réponse obtenue est trop éloignée de la réponse attendue.",
        "sourcePresent": "Aucune source n'accompagne la réponse trouvée.",
        "documentMatch": "Aucun document attendu n'a été retrouvé.",
        "pageMatch": "Aucune page attendue n'a été retrouvée.",
        "sectionMatch": "Aucune section attendue n'a été retrouvée.",
        "grounded": "Au moins une affirmation n'est pas suffisamment étayée par les sources.",
    }
    failures = [reason_labels[name] for name, passed in checks.items() if not passed]
    return checks, failures, reference_recall


def _active_document_records(db: Session) -> list[dict]:
    documents = db.scalars(
        select(Document).where(Document.active.is_(True)).order_by(Document.file_name)
    ).all()
    return [
        {"id": str(document.id), "title": document.title, "fileName": document.file_name}
        for document in documents
    ]


def _document_is_covered(document: dict, results: list[EvaluationResult]) -> bool:
    aliases = {_normalize(document["id"]), _normalize(document["title"]), _normalize(document["fileName"])}
    for result in results:
        expected = {_normalize(value) for value in (result.expected_documents or [])}
        if not aliases & expected or result.retrieval_rank is None or result.retrieval_rank > 5:
            continue
        if any(aliases & _document_aliases(record) for record in (result.retrieved_documents or [])):
            return True
    return False


def _aggregate_run(run: EvaluationRun, results: list[EvaluationResult], documents: list[dict]) -> None:
    latencies = [result.latency_ms for result in results]
    retrieval_latencies = [
        result.retrieval_latency_ms for result in results
        if result.retrieval_latency_ms is not None
    ]
    eligible = [result for result in results if result.recall_at_5 is not None]
    run.latency_p50_ms = _percentile(latencies, 0.50)
    run.latency_p95_ms = _percentile(latencies, 0.95)
    run.retrieval_latency_p50_ms = _percentile(retrieval_latencies, 0.50)
    run.retrieval_latency_p95_ms = _percentile(retrieval_latencies, 0.95)
    if eligible:
        run.recall_at_1 = round(sum(bool(item.recall_at_1) for item in eligible) / len(eligible), 4)
        run.recall_at_3 = round(sum(bool(item.recall_at_3) for item in eligible) / len(eligible), 4)
        run.recall_at_5 = round(sum(bool(item.recall_at_5) for item in eligible) / len(eligible), 4)
        run.mrr = round(sum(item.reciprocal_rank or 0.0 for item in eligible) / len(eligible), 4)
    covered = [document for document in documents if _document_is_covered(document, results)]
    run.active_documents_total = len(documents)
    run.covered_documents_total = len(covered)
    run.document_coverage_percent = round(len(covered) / len(documents) * 100, 2) if documents else 100.0
    covered_ids = {item["id"] for item in covered}
    run.uncovered_documents = [item for item in documents if item["id"] not in covered_ids]
    technically_successful = [result for result in results if result.error is None]
    failed = [result for result in results if result.error is not None]
    timeout_results = [
        result for result in results
        if "timeout" in (result.error or "").lower()
        or any(call.get("timeout") for call in ((result.diagnostics or {}).get("llmCalls") or []))
    ]
    successful_latencies = [result.latency_ms for result in technically_successful]
    llm_calls = [
        call
        for result in results
        for call in ((result.diagnostics or {}).get("llmCalls") or [])
    ]
    output_tokens = [
        call["outputTokens"] for call in llm_calls
        if call.get("outputTokens") is not None
    ]
    embedding_calls = [
        call
        for result in results
        for call in ((result.diagnostics or {}).get("attributes", {}).get("embeddingCalls") or [])
    ]
    embedding_durations = [
        float(call["elapsedMs"]) for call in embedding_calls
        if call.get("elapsedMs") is not None
    ]
    run.diagnostics = {
        "successfulRequests": len(technically_successful),
        "failedRequests": len(failed),
        "timeoutCount": len(timeout_results),
        "timeoutRate": round(len(timeout_results) / len(results), 4) if results else 0.0,
        "successfulLatencyP50Ms": _percentile(successful_latencies, 0.50),
        "successfulLatencyP95Ms": _percentile(successful_latencies, 0.95),
        "allRequestsLatencyP50Ms": run.latency_p50_ms,
        "allRequestsLatencyP95Ms": run.latency_p95_ms,
        "llmCallCount": len(llm_calls),
        "outputTokensP50": _percentile(output_tokens, 0.50),
        "outputTokensP95": _percentile(output_tokens, 0.95),
        "outputTokensMax": max(output_tokens) if output_tokens else None,
        "embeddingCallCount": len(embedding_calls),
        "embeddingTotalDurationMs": round(sum(embedding_durations), 3),
        "embeddingP50Ms": _percentile(embedding_durations, 0.50),
        "embeddingP95Ms": _percentile(embedding_durations, 0.95),
        "embeddingMaxMs": max(embedding_durations) if embedding_durations else None,
        "itemsPerEmbeddingCall": [call.get("itemCount") for call in embedding_calls],
    }


def run_evaluation_campaign(
    db: Session,
    initiated_by: str | None,
    dataset_split: str = "calibration",
) -> EvaluationRun:
    if dataset_split not in DATASET_SPLITS:
        raise ValueError(f"Jeu d'évaluation non supporté : {dataset_split}")
    query = select(EvaluationQuestion).where(EvaluationQuestion.active.is_(True))
    if dataset_split != "all":
        query = query.where(EvaluationQuestion.dataset_split == dataset_split)
    questions = db.scalars(query.order_by(EvaluationQuestion.code)).all()
    documents = _active_document_records(db)
    run = EvaluationRun(
        status="running",
        dataset_split=dataset_split,
        total=len(questions),
        initiated_by=initiated_by,
        active_documents_total=len(documents),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    if not questions:
        run.status = "failed"
        run.error = "Aucune question de référence active pour ce jeu."
        run.completed_at = datetime.now(timezone.utc)
        run.duration_ms = 0
        db.commit()
        db.refresh(run)
        return run

    campaign_started = time.perf_counter()
    service = get_rag_service()
    passed = 0
    persisted_results = []
    if RAG_EVALUATION_CONCURRENCY != 1:
        raise ValueError(
            "La campagne de référence synchrone exige RAG_EVALUATION_CONCURRENCY=1."
        )
    try:
        for question in questions:
            case_started = time.perf_counter()
            with trace_question(question.code, question.question) as trace:
                try:
                    with question_deadline(RAG_QUESTION_TIMEOUT_SECONDS):
                        set_trace_attribute("deadlineConfiguredSeconds", RAG_QUESTION_TIMEOUT_SECONDS)
                        history = [SimpleNamespace(**message) for message in (question.history or [])]
                        retrieval_question = contextualize_question(question.question, history, service.llm)
                        record_trace_event(
                            "memory_end", contextualized=retrieval_question != question.question
                        )
                        set_trace_attribute("retrievalQuestion", retrieval_question)
                        rag_result = service.answer_question(retrieval_question)
                        retrieved_records = [
                            _node_record(node) for node in rag_result.retrieved_nodes[:5]
                        ]
                        retrieval = _retrieval_metrics(question, retrieved_records)
                        with timed_step("evaluation_validation"):
                            checks, failures, similarity = _evaluate_checks(question, rag_result)
                        success = all(checks.values())
                        passed += int(success)
                        sources = _serialize_sources(rag_result.sources)
                        actual_pages = sorted({page for source in rag_result.sources for page in source.pages})
                        evaluation_result = EvaluationResult(
                            run_id=run.id, question_id=question.id, question_code=question.code,
                            category=question.category, dataset_split=question.dataset_split,
                            question_text=question.question, expected_status=question.expected_status,
                            expected_answer=question.expected_answer, actual_status=rag_result.status,
                            actual_answer=rag_result.answer, expected_pages=question.expected_pages,
                            expected_documents=question.expected_documents, actual_pages=actual_pages,
                            retrieved_documents=retrieved_records, retrieval_rank=retrieval["rank"],
                            recall_at_1=retrieval["recall1"], recall_at_3=retrieval["recall3"],
                            recall_at_5=retrieval["recall5"], reciprocal_rank=retrieval["reciprocalRank"],
                            retrieval_latency_ms=rag_result.retrieval_latency_ms,
                            sources=sources, checks=checks,
                            failure_reasons=failures, confidence_score=rag_result.confidence_score,
                            answer_similarity=similarity,
                            latency_ms=round((time.perf_counter() - case_started) * 1000), success=success,
                        )
                except Exception as exc:
                    is_timeout = isinstance(exc, QuestionTimeoutError) or "timeout" in type(exc).__name__.lower()
                    set_trace_attribute("errorType", "TIMEOUT" if is_timeout else type(exc).__name__)
                    if isinstance(exc, QuestionTimeoutError):
                        set_trace_attribute("timeoutStage", exc.stage)
                        set_trace_attribute("deadlineConfiguredSeconds", exc.timeout_seconds)
                    evaluation_result = EvaluationResult(
                        run_id=run.id, question_id=question.id, question_code=question.code,
                        category=question.category, dataset_split=question.dataset_split,
                        question_text=question.question, expected_status=question.expected_status,
                        actual_status="TIMEOUT" if is_timeout else None,
                        expected_answer=question.expected_answer, expected_pages=question.expected_pages,
                        expected_documents=question.expected_documents, actual_pages=[],
                        retrieved_documents=[], sources=[],
                        checks={name: False for name in (
                            "statusMatch", "requiredTermsMatch", "answerReferenceMatch",
                            "sourcePresent", "documentMatch", "pageMatch", "sectionMatch", "grounded",
                        )},
                        failure_reasons=[
                            "Deadline globale dépassée." if is_timeout
                            else "Erreur technique pendant l'évaluation."
                        ],
                        latency_ms=round((time.perf_counter() - case_started) * 1000),
                        success=False,
                        error=(f"TIMEOUT: {exc}" if is_timeout else f"{type(exc).__name__}: {exc}"),
                    )
            evaluation_result.diagnostics = trace.to_dict()
            db.add(evaluation_result)
            db.commit()
            db.refresh(evaluation_result)
            persisted_results.append(evaluation_result)
        run.status = "completed"
    except Exception as exc:
        run.status = "failed"
        run.error = f"{type(exc).__name__}: {exc}"
    finally:
        run.passed = passed
        run.score_percent = round(passed / max(run.total, 1) * 100, 2)
        run.duration_ms = round((time.perf_counter() - campaign_started) * 1000)
        run.completed_at = datetime.now(timezone.utc)
        _aggregate_run(run, persisted_results, documents)
        db.commit()
        db.refresh(run)
    return run
