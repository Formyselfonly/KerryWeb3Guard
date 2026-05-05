from fastapi import APIRouter

from app.schemas.learn import LearnRequest, LearnResponse
from app.services.learn import LearnService

router = APIRouter(prefix="/learn", tags=["learn"])

learn_service = LearnService()


@router.post("/web3", response_model=LearnResponse)
async def learn_web3(payload: LearnRequest) -> LearnResponse:
    return await learn_service.generate(payload)
