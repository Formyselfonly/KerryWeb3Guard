from pydantic import BaseModel


class KeyCheckResult(BaseModel):
    configured: bool
    valid: bool
    message: str


class KeyVerificationResponse(BaseModel):
    openai: KeyCheckResult
    bitquery: KeyCheckResult


class StartGuideItem(BaseModel):
    text: str
    source: str


class StartGuideResponse(BaseModel):
    scam_knowledge: list[StartGuideItem]
    legit_company_practices: list[StartGuideItem]


class ScamPatternPlaybookItem(BaseModel):
    pattern_id: str
    name: str
    scenario: str
    red_flags: list[str]
    safe_actions: list[str]


class ScamPatternPlaybookResponse(BaseModel):
    pattern_catalog: list[ScamPatternPlaybookItem]
