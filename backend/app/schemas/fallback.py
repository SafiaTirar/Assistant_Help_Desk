from pydantic import BaseModel


class FallbackItem(BaseModel):
    id: str
    question: str
    occurrences: int
    first: str
    last: str
    status: str
    comment: str


class FallbackUpdateRequest(BaseModel):
    status: str | None = None
    comment: str | None = None
