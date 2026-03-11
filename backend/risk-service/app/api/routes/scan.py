from fastapi import APIRouter

from app.schemas.chat import ChatScanRequest, ChatScanResponse
from app.schemas.contract import ContractScanRequest, ContractScanResponse
from app.schemas.link import LinkScanRequest, LinkScanResponse
from app.services.chat_scan import ChatScanService
from app.services.contract_scan import ContractScanService
from app.services.link_scan import LinkScanService

router = APIRouter(prefix="/scan", tags=["scan"])

contract_service = ContractScanService()
link_service = LinkScanService()
chat_service = ChatScanService()


@router.post("/contract", response_model=ContractScanResponse)
async def scan_contract(payload: ContractScanRequest) -> ContractScanResponse:
    return await contract_service.scan(payload)


@router.post("/link", response_model=LinkScanResponse)
async def scan_link(payload: LinkScanRequest) -> LinkScanResponse:
    return await link_service.scan(payload)


@router.post("/chat", response_model=ChatScanResponse)
async def scan_chat(payload: ChatScanRequest) -> ChatScanResponse:
    return await chat_service.scan(payload)
