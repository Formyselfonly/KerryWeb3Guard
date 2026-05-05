from pydantic import BaseModel, Field

from app.schemas.common import BaseScanResponse, Language


class ChatScanRequest(BaseModel):
    chat_text: str = Field(min_length=5)
    response_language: Language = "en"


class ChatScanResponse(BaseScanResponse):
    scam_type: str
    evidence_points: list[str]
    recommended_action: str
