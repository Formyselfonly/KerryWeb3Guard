from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import Language

ReviewStatus = Literal["submitted", "under_review", "listed", "rejected"]


class BlacklistReportRequest(BaseModel):
    reporter_contact: str = Field(min_length=2, max_length=120)
    platform: str = Field(min_length=2, max_length=40)
    suspected_handle: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=10, max_length=5000)
    evidence_links: list[str] = []
    response_language: Language = "en"


class BlacklistCase(BaseModel):
    case_id: str
    scammer_display_name: str
    platform: str
    contact_handle: str
    evidence_summary: str
    review_status: ReviewStatus
    updated_at: datetime


class BlacklistReportResponse(BaseModel):
    message: str
    case: BlacklistCase


class BlacklistReviewRequest(BaseModel):
    review_status: ReviewStatus
    scammer_display_name: str | None = Field(default=None, max_length=120)
    evidence_summary: str | None = Field(default=None, max_length=2000)
