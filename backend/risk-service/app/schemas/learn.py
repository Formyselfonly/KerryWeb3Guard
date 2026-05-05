from pydantic import BaseModel, Field

from app.schemas.common import Language


class LearnRequest(BaseModel):
    topic: str | None = Field(default=None, max_length=120)
    user_question: str | None = Field(default=None, max_length=5000)
    response_language: Language = "en"


class LearnResponse(BaseModel):
    module: str = "web3_learning_hub"
    title: str
    summary: str
    key_points: list[str]
    action_checklist: list[str]
    quiz_questions: list[str] = []


class ScamPatternGuideRequest(BaseModel):
    pattern_id: str | None = Field(default=None, max_length=80)
    user_question: str | None = Field(default=None, max_length=5000)
    response_language: Language = "en"


class ScamPatternCard(BaseModel):
    pattern_id: str
    name: str
    scenario: str
    red_flags: list[str]
    safe_actions: list[str]


class ScamPatternGuideResponse(BaseModel):
    module: str = "scam_pattern_learning_guide"
    topic: str
    intro: str
    pattern_catalog: list[ScamPatternCard]
    selected_pattern_id: str
    explanation: str
    interactive_checklist: list[str]
    next_questions: list[str]
