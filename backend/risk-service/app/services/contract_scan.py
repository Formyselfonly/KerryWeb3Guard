from app.providers.bitquery import BitqueryProvider
from app.providers.dexscreener import DexScreenerProvider
from app.providers.llm import LLMProvider
from app.providers.source_code import SourceCodeProvider
from app.schemas.contract import (
    ContractMetrics,
    ContractScanRequest,
    ContractScanResponse,
    HolderMetrics,
    LPMetrics,
    SourceCodeMetrics,
    TradingMetrics,
)


class ContractScanService:
    def __init__(self) -> None:
        self.dexscreener = DexScreenerProvider()
        self.bitquery = BitqueryProvider()
        self.source_code = SourceCodeProvider()
        self.llm = LLMProvider()

    async def scan(self, request: ContractScanRequest) -> ContractScanResponse:
        snapshot = await self.dexscreener.fetch_token_snapshot(
            request.contract_address,
            request.chain,
        )
        source_check = await self.source_code.check_contract_source(
            request.chain,
            request.contract_address,
        )
        bitquery_metrics = await self.bitquery.fetch_holder_and_lp_metrics(
            chain=request.chain,
            token_address=request.contract_address,
            lp_address=snapshot.get("pair_address"),
        )
        data_warnings: list[str] = []
        if not snapshot.get("matched_chain", False):
            data_warnings.append(
                "No direct pair matched selected chain; fallback pair was used."
            )
        data_warnings.extend(bitquery_metrics.get("warnings", []))
        if source_check.get("status") == "unknown":
            data_warnings.append(
                "Source code verification is unavailable for this chain."
            )

        metrics = ContractMetrics(
            trading=TradingMetrics(
                buy_count_24h=snapshot.get("buy_count_24h", 0),
                sell_count_24h=snapshot.get("sell_count_24h", 0),
                buy_volume_usd_24h=None,
                sell_volume_usd_24h=None,
                total_volume_usd_24h=float(snapshot.get("volume_usd_24h", 0)),
            ),
            holders=HolderMetrics(
                top_10_ratio_percent=bitquery_metrics.get("top_10_ratio_percent"),
                others_ratio_percent=bitquery_metrics.get("others_ratio_percent"),
                note=(
                    "Holder metrics are powered by Bitquery when available."
                ),
            ),
            lp=LPMetrics(
                pair_count=snapshot.get("pair_count", 0),
                liquidity_usd=float(snapshot.get("liquidity_usd", 0)),
                lp_provider_count=bitquery_metrics.get("lp_provider_count"),
                lp_locked_ratio_percent=bitquery_metrics.get(
                    "lp_locked_ratio_percent"
                ),
            ),
            source_code=SourceCodeMetrics(
                is_public=source_check.get("is_public"),
                status=source_check.get("status", "unknown"),
                source_platform=source_check.get("source_platform"),
                check_url=source_check.get("check_url"),
                note=source_check.get("note", ""),
            ),
        )

        payload = {
            "chain": request.chain,
            "contract_address": request.contract_address,
            "response_language": request.response_language,
            "signals": metrics.model_dump(),
            "available_chains": snapshot.get("available_chains", []),
            "data_warnings": data_warnings,
        }
        system_prompt = (
            "You are a Web3 contract risk analyst.\n"
            "Reply in response_language. Return JSON with keys:\n"
            "risk_score (0-100 integer), summary, reasons (array), advice."
        )
        fallback = {
            "risk_score": 50,
            "summary": "LLM is not configured; this is a placeholder result.",
            "reasons": [
                "OPENAI_API_KEY is missing or response parsing failed.",
                "Configure .env and retry for full AI analysis.",
            ],
            "advice": "Do not trade before running AI analysis successfully.",
        }
        result = await self.llm.run_json_analysis(system_prompt, payload, fallback)
        normalized_result = self._normalize_llm_result(result, fallback)
        return ContractScanResponse(
            module="contract_risk_scan",
            metrics=metrics,
            data_warnings=data_warnings,
            **normalized_result,
        )

    @staticmethod
    def _normalize_llm_result(
        result: dict,
        fallback: dict,
    ) -> dict:
        score_raw = result.get("risk_score", fallback["risk_score"])
        try:
            risk_score = int(score_raw)
        except (TypeError, ValueError):
            risk_score = int(fallback["risk_score"])
        risk_score = max(0, min(100, risk_score))

        summary_raw = result.get("summary", fallback["summary"])
        summary = (
            summary_raw
            if isinstance(summary_raw, str)
            else str(summary_raw)
        )

        reasons_raw = result.get("reasons", fallback["reasons"])
        if isinstance(reasons_raw, list):
            reasons = [str(item) for item in reasons_raw]
        elif isinstance(reasons_raw, str):
            reasons = [reasons_raw]
        else:
            reasons = list(fallback["reasons"])

        advice_raw = result.get("advice", fallback["advice"])
        if isinstance(advice_raw, list):
            advice = " ".join(str(item) for item in advice_raw if item is not None)
        elif isinstance(advice_raw, str):
            advice = advice_raw
        else:
            advice = str(advice_raw)

        if not advice.strip():
            advice = fallback["advice"]

        return {
            "risk_score": risk_score,
            "summary": summary,
            "reasons": reasons,
            "advice": advice,
        }
