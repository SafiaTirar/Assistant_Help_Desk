from pydantic import BaseModel, Field


class MetricResponse(BaseModel):
    total: int
    found: int
    unanswered: int
    out_of_scope: int = Field(alias="outOfScope")
    positive: str
    negative: str
    average: str


class StatusStat(BaseModel):
    label: str
    value: int


class TopQuestion(BaseModel):
    question: str
    occurrences: int
    status: str


class AttentionItem(BaseModel):
    question: str
    occurrences: int
    reason: str


class DashboardResponse(BaseModel):
    metrics: MetricResponse
    trend: list[int]
    trend_labels: list[str] = Field(alias="trendLabels")
    statuses: list[StatusStat]
    top_questions: list[TopQuestion] = Field(alias="topQuestions")
    attention: list[AttentionItem]


class AdminConversationResponse(BaseModel):
    id: str
    date: str
    user: str
    question: str
    status: str
    answer: str
    feedback: str
    duration: str
    internal_references: list[dict] = Field(alias="internalReferences")
