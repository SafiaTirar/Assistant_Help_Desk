from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EvaluationQuestionBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    code: str = Field(min_length=1, max_length=40)
    category: str = Field(min_length=1, max_length=80)
    dataset_split: str = Field(default="calibration", alias="datasetSplit")
    question: str = Field(min_length=3)
    expected_status: str = Field(alias="expectedStatus")
    expected_answer: str = Field(default="", alias="expectedAnswer")
    expected_pages: list[int] = Field(default_factory=list, alias="expectedPages")
    expected_sections: list[str] = Field(default_factory=list, alias="expectedSections")
    expected_documents: list[str] = Field(default_factory=list, alias="expectedDocuments")
    required_terms: list[str] = Field(default_factory=list, alias="requiredTerms")
    history: list[dict] = Field(default_factory=list)
    active: bool = True


class EvaluationQuestionCreate(EvaluationQuestionBase):
    pass


class EvaluationQuestionUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    code: str | None = Field(default=None, min_length=1, max_length=40)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    dataset_split: str | None = Field(default=None, alias="datasetSplit")
    question: str | None = Field(default=None, min_length=3)
    expected_status: str | None = Field(default=None, alias="expectedStatus")
    expected_answer: str | None = Field(default=None, alias="expectedAnswer")
    expected_pages: list[int] | None = Field(default=None, alias="expectedPages")
    expected_sections: list[str] | None = Field(default=None, alias="expectedSections")
    expected_documents: list[str] | None = Field(default=None, alias="expectedDocuments")
    required_terms: list[str] | None = Field(default=None, alias="requiredTerms")
    history: list[dict] | None = None
    active: bool | None = None


class EvaluationQuestionResponse(EvaluationQuestionBase):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class EvaluationImportRequest(BaseModel):
    questions: list[EvaluationQuestionCreate]


class EvaluationImportResponse(BaseModel):
    created: int
    updated: int
    total: int


class EvaluationRunCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    dataset_split: str = Field(default="calibration", alias="datasetSplit")


class EvaluationResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    question_id: UUID | None = Field(alias="questionId")
    question_code: str = Field(alias="questionCode")
    category: str
    dataset_split: str = Field(alias="datasetSplit")
    question_text: str = Field(alias="question")
    expected_status: str = Field(alias="expectedStatus")
    expected_answer: str = Field(alias="expectedAnswer")
    actual_status: str | None = Field(alias="actualStatus")
    actual_answer: str = Field(alias="actualAnswer")
    expected_pages: list[int] = Field(alias="expectedPages")
    expected_documents: list[str] = Field(alias="expectedDocuments")
    actual_pages: list[int] = Field(alias="actualPages")
    retrieved_documents: list[dict] = Field(alias="retrievedDocuments")
    retrieval_rank: int | None = Field(alias="retrievalRank")
    recall_at_1: bool | None = Field(alias="recallAt1")
    recall_at_3: bool | None = Field(alias="recallAt3")
    recall_at_5: bool | None = Field(alias="recallAt5")
    reciprocal_rank: float | None = Field(alias="reciprocalRank")
    retrieval_latency_ms: int | None = Field(alias="retrievalLatencyMs")
    sources: list[dict]
    checks: dict
    failure_reasons: list[str] = Field(alias="failureReasons")
    confidence_score: float | None = Field(alias="confidenceScore")
    answer_similarity: float | None = Field(alias="answerSimilarity")
    latency_ms: int = Field(alias="latencyMs")
    success: bool
    error: str | None
    diagnostics: dict | None = None


class EvaluationRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    status: str
    dataset_split: str = Field(alias="datasetSplit")
    total: int
    passed: int
    score_percent: float = Field(alias="scorePercent")
    duration_ms: int | None = Field(alias="durationMs")
    latency_p50_ms: int | None = Field(alias="latencyP50Ms")
    latency_p95_ms: int | None = Field(alias="latencyP95Ms")
    retrieval_latency_p50_ms: int | None = Field(alias="retrievalLatencyP50Ms")
    retrieval_latency_p95_ms: int | None = Field(alias="retrievalLatencyP95Ms")
    recall_at_1: float | None = Field(alias="recallAt1")
    recall_at_3: float | None = Field(alias="recallAt3")
    recall_at_5: float | None = Field(alias="recallAt5")
    mrr: float | None
    active_documents_total: int = Field(alias="activeDocumentsTotal")
    covered_documents_total: int = Field(alias="coveredDocumentsTotal")
    document_coverage_percent: float = Field(alias="documentCoveragePercent")
    uncovered_documents: list[dict] = Field(alias="uncoveredDocuments")
    diagnostics: dict | None = None
    initiated_by: str | None = Field(alias="initiatedBy")
    error: str | None
    started_at: datetime = Field(alias="startedAt")
    completed_at: datetime | None = Field(alias="completedAt")


class EvaluationRunDetail(EvaluationRunSummary):
    results: list[EvaluationResultResponse]
