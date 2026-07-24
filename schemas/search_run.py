from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SearchRunCreate(BaseModel):
    query: str = Field(min_length=3, max_length=2000)
    category: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default="Россия", max_length=100)
    region: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    keywords: list[str] = Field(default_factory=list, max_length=30)
    excluded_keywords: list[str] = Field(default_factory=list, max_length=30)
    search_queries_limit: int = Field(default=8, ge=1, le=12)
    requested_limit: int = Field(default=20, ge=1, le=100)
    min_relevance_score: int = Field(default=50, ge=0, le=100)


class SearchRunRead(SearchRunCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    search_queries: list[str]
    found_count: int
    raw_result_count: int
    executed_query_count: int
    saved_count: int
    duplicate_count: int
    error_count: int
    agent_result: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
