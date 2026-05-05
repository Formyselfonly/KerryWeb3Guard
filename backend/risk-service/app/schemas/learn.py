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
