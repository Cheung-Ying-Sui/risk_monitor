from pydantic import BaseModel, Field


class SanctionsSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=300)
    entity_type: str = "all"
    sanctions_list: str = "OFAC"
    mode: str = "standard"


class SanctionsMatch(BaseModel):
    profile_id: str
    source: str
    names: list[str]
    addresses: list[str]
    programs: list[str]
    matched_name: str
    match_type: str
    score: float


class SanctionsSuggestion(BaseModel):
    name: str
    score: float


class AiAssistedCandidate(BaseModel):
    query: str
    reason: str
    ai_probability: float | None = None
    matched_name: str | None = None
    match_score: float | None = None
    profile_id: str | None = None
    programs: list[str] = Field(default_factory=list)
    formal_match: bool = False


class SanctionsSearchResponse(BaseModel):
    keyword: str
    normalized_keyword: str
    results: list[SanctionsMatch]
    suggestions: list[SanctionsSuggestion]
    ai_candidates: list[AiAssistedCandidate] = Field(default_factory=list)
    ai_message: str | None = None
    message: str | None = None


class PartyManualReviewRequest(BaseModel):
    result: str
    reviewer: str = Field(min_length=1, max_length=120)
    note: str = Field(default="", max_length=2000)
