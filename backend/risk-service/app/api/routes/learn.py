from fastapi import APIRouter

from app.schemas.learn import (
    LearnRequest,
    LearnResponse,
    ScamPatternGuideRequest,
    ScamPatternGuideResponse,
)
from app.services.learn import LearnService

router = APIRouter(prefix="/learn", tags=["learn"])

learn_service = LearnService()


@router.post("/web3", response_model=LearnResponse)
async def learn_web3(payload: LearnRequest) -> LearnResponse:
    return await learn_service.generate(payload)


@router.post("/scam-patterns", response_model=ScamPatternGuideResponse)
async def learn_scam_patterns(
    payload: ScamPatternGuideRequest,
) -> ScamPatternGuideResponse:
    return await learn_service.generate_scam_pattern_guide(payload)
