from typing import Literal

from pydantic import BaseModel, Field

Language = Literal["en", "zh-CN"]


class BaseScanResponse(BaseModel):
    module: str
    risk_score: int = Field(ge=0, le=100)
    summary: str


class HealthResponse(BaseModel):
    status: str
