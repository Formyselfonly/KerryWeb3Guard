from typing import Any

import httpx

from app.core.settings import get_settings


class DexScreenerProvider:
    async def fetch_token_snapshot(
        self,
        contract_address: str,
        chain: str,
    ) -> dict[str, Any]:
        settings = get_settings()
        url = (
            f"{settings.dexscreener_base_url}/latest/dex/tokens/{contract_address}"
        )
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

        pairs = data.get("pairs") or []
        if not pairs:
            return {
                "pair_count": 0,
                "matched_chain": False,
                "available_chains": [],
                "dex_id": None,
                "chain_id": chain,
                "liquidity_usd": 0,
                "buy_count_24h": 0,
                "sell_count_24h": 0,
                "volume_usd_24h": 0,
                "price_change_24h": 0,
            }

        filtered_pairs = [item for item in pairs if item.get("chainId") == chain]
        selected_pair = filtered_pairs[0] if filtered_pairs else pairs[0]
        available_chains = sorted(
            {item.get("chainId") for item in pairs if item.get("chainId")}
        )

        primary_pair = selected_pair
        txns_24h = primary_pair.get("txns", {}).get("h24", {})
        liquidity = primary_pair.get("liquidity", {})

        return {
            "pair_count": len(pairs),
            "matched_chain": bool(filtered_pairs),
            "available_chains": available_chains,
            "pair_address": primary_pair.get("pairAddress"),
            "dex_id": primary_pair.get("dexId"),
            "chain_id": primary_pair.get("chainId"),
            "liquidity_usd": liquidity.get("usd", 0),
            "buy_count_24h": txns_24h.get("buys", 0),
            "sell_count_24h": txns_24h.get("sells", 0),
            "volume_usd_24h": primary_pair.get("volume", {}).get("h24", 0),
            "price_change_24h": primary_pair.get("priceChange", {}).get("h24", 0),
        }
