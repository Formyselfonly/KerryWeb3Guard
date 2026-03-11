from pydantic import BaseModel


class KeyCheckResult(BaseModel):
    configured: bool
    valid: bool
    message: str


class KeyVerificationResponse(BaseModel):
    openai: KeyCheckResult
    bitquery: KeyCheckResult
