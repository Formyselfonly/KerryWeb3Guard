from pydantic import BaseModel, Field

from app.schemas.common import BaseScanResponse, Language


class LinkScanRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    response_language: Language = "en"


class LinkScanResponse(BaseScanResponse):
    reasons: list[str]
    advice: str
