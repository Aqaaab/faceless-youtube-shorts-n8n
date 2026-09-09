from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str = Field(min_length=1)
    url: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    title: str = Field(min_length=1)
    retrieved_at: str = Field(min_length=1)
    authority: float = Field(ge=0.0, le=1.0)


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str = Field(min_length=1)
    excerpt: str = Field(min_length=1)
    supports: bool


class ResearchFact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim: str = Field(min_length=1)
    field: str = Field(min_length=1)
    value: str | float | int | bool
    unit: str | None = None
    evidence: list[Evidence] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    status: str = "UNVERIFIED"


class ResearchBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topic: str = Field(min_length=1)
    sources: list[Source] = Field(default_factory=list)
    facts: list[ResearchFact] = Field(default_factory=list)
    rejected_claims: list[str] = Field(default_factory=list)
