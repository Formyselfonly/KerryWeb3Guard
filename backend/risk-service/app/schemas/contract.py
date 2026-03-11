from pydantic import BaseModel, Field
from pydantic import field_validator

from app.core.settings import get_settings
from app.schemas.common import BaseScanResponse, Language


class ContractScanRequest(BaseModel):
    chain: str = Field(min_length=2, max_length=32)
    contract_address: str = Field(min_length=4, max_length=128)
    response_language: Language = "en"

    @field_validator("chain")
    @classmethod
    def validate_chain(cls, value: str) -> str:
        supported = {
            item.strip().lower()
            for item in get_settings().dexscreener_supported_chains.split(",")
            if item.strip()
        }
        normalized = value.strip().lower()
        if normalized not in supported:
            raise ValueError("Unsupported chain for DexScreener chain parameter.")
        return normalized


class TradingMetrics(BaseModel):
    buy_count_24h: int
    sell_count_24h: int
    buy_volume_usd_24h: float | None = None
    sell_volume_usd_24h: float | None = None
    total_volume_usd_24h: float


class HolderMetrics(BaseModel):
    top_10_ratio_percent: float | None = None
    others_ratio_percent: float | None = None
    note: str


class LPMetrics(BaseModel):
    pair_count: int
    liquidity_usd: float
    lp_provider_count: int | None = None
    lp_locked_ratio_percent: float | None = None


class SourceCodeMetrics(BaseModel):
    is_public: bool | None = None
    status: str
    source_platform: str | None = None
    check_url: str | None = None
    note: str


class ContractMetrics(BaseModel):
    trading: TradingMetrics
    holders: HolderMetrics
    lp: LPMetrics
    source_code: SourceCodeMetrics


class ContractScanResponse(BaseScanResponse):
    metrics: ContractMetrics
    data_warnings: list[str] = []
    reasons: list[str]
    advice: str
