from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.settings import get_settings

BITQUERY_NETWORK_BY_CHAIN: dict[str, str] = {
    "ethereum": "eth",
    "bsc": "bsc",
    "polygon": "matic",
    "arbitrum": "arbitrum",
    "optimism": "optimism",
    "base": "base",
    "avalanche": "avalanche",
    "fantom": "fantom",
    "linea": "linea",
    "blast": "blast",
    "zksync": "zksync",
    "mantle": "mantle",
    "scroll": "scroll",
    "sei": "sei",
}


class BitqueryProvider:
    async def fetch_holder_and_lp_metrics(
        self,
        chain: str,
        token_address: str,
        lp_address: str | None,
    ) -> dict[str, Any]:
        settings = get_settings()
        if not settings.bitquery_api_key:
            return {
                "holders_found": False,
                "lp_found": False,
                "top_10_ratio_percent": None,
                "others_ratio_percent": None,
                "lp_provider_count": None,
                "lp_locked_ratio_percent": None,
                "warnings": ["BITQUERY_API_KEY is missing."],
            }

        network = BITQUERY_NETWORK_BY_CHAIN.get(chain)
        if not network:
            return {
                "holders_found": False,
                "lp_found": False,
                "top_10_ratio_percent": None,
                "others_ratio_percent": None,
                "lp_provider_count": None,
                "lp_locked_ratio_percent": None,
                "warnings": ["Bitquery network mapping is unavailable for this chain."],
            }

        date = datetime.now(UTC).date().isoformat()
        holders = await self._fetch_token_holders(network, token_address, date)
        lp = (
            await self._fetch_lp_provider_count(network, lp_address, date)
            if lp_address
            else {"lp_provider_count": None, "warning": "LP pair address is missing."}
        )

        warnings: list[str] = []
        if holders.get("warning"):
            warnings.append(str(holders["warning"]))
        if lp.get("warning"):
            warnings.append(str(lp["warning"]))

        return {
            "holders_found": holders.get("top_10_ratio_percent") is not None,
            "lp_found": lp.get("lp_provider_count") is not None,
            "top_10_ratio_percent": holders.get("top_10_ratio_percent"),
            "others_ratio_percent": holders.get("others_ratio_percent"),
            "lp_provider_count": lp.get("lp_provider_count"),
            "lp_locked_ratio_percent": None,
            "warnings": warnings,
        }

    async def _fetch_token_holders(
        self,
        network: str,
        token_address: str,
        date: str,
    ) -> dict[str, Any]:
        query_template = """
query TokenHolders($token: String!, $date: String!) {
  EVM(dataset: archive, network: __NETWORK__) {
    top: TokenHolders(
      date: $date
      tokenSmartContract: $token
      where: {Balance: {Amount: {gt: "0"}}}
      orderBy: {descending: Balance_Amount}
      limit: {count: 10}
    ) {
      Balance {
        Amount
      }
    }
    total: TokenHolders(
      date: $date
      tokenSmartContract: $token
      where: {Balance: {Amount: {gt: "0"}}}
    ) {
      total_amount: sum(of: Balance_Amount)
    }
  }
}
"""
        query = query_template.replace("__NETWORK__", network)
        payload = await self._post_graphql(
            query=query,
            variables={"token": token_address, "date": date},
        )
        if payload.get("errors"):
            return {"warning": f"Bitquery holders query failed: {payload['errors'][0]}"}

        evm = (payload.get("data") or {}).get("EVM") or {}
        top_rows = evm.get("top") or []
        total_rows = evm.get("total") or []

        top_sum = 0.0
        for row in top_rows:
            amount = ((row or {}).get("Balance") or {}).get("Amount")
            try:
                top_sum += float(amount)
            except (TypeError, ValueError):
                continue

        total_amount = 0.0
        if total_rows:
            raw_total = (total_rows[0] or {}).get("total_amount")
            try:
                total_amount = float(raw_total)
            except (TypeError, ValueError):
                total_amount = 0.0

        if total_amount <= 0:
            return {"warning": "Bitquery returned empty holder totals."}

        top_ratio = round((top_sum / total_amount) * 100, 2)
        return {
            "top_10_ratio_percent": top_ratio,
            "others_ratio_percent": round(100 - top_ratio, 2),
        }

    async def _fetch_lp_provider_count(
        self,
        network: str,
        lp_address: str,
        date: str,
    ) -> dict[str, Any]:
        query_template = """
query LPProviders($token: String!, $date: String!) {
  EVM(dataset: archive, network: __NETWORK__) {
    providers: TokenHolders(
      date: $date
      tokenSmartContract: $token
      where: {Balance: {Amount: {gt: "0"}}}
    ) {
      count: uniq(of: Holder_Address)
    }
  }
}
"""
        query = query_template.replace("__NETWORK__", network)
        payload = await self._post_graphql(
            query=query,
            variables={"token": lp_address, "date": date},
        )
        if payload.get("errors"):
            return {"warning": f"Bitquery LP query failed: {payload['errors'][0]}"}

        evm = (payload.get("data") or {}).get("EVM") or {}
        rows = evm.get("providers") or []
        if not rows:
            return {"warning": "Bitquery returned empty LP provider data."}
        raw_count = (rows[0] or {}).get("count")
        try:
            return {"lp_provider_count": int(raw_count)}
        except (TypeError, ValueError):
            return {"warning": "Bitquery LP provider count parsing failed."}

    async def _post_graphql(
        self,
        query: str,
        variables: dict[str, Any],
    ) -> dict[str, Any]:
        settings = get_settings()
        header_candidates = _bitquery_header_candidates(
            api_key=settings.bitquery_api_key,
            endpoint=settings.bitquery_endpoint,
        )
        async with httpx.AsyncClient(timeout=20.0) as client:
            response: httpx.Response | None = None
            for headers in header_candidates:
                response = await client.post(
                    settings.bitquery_endpoint,
                    json={"query": query, "variables": variables},
                    headers=headers,
                )
                # Accept first non-auth failure response.
                if response.status_code not in (401, 403):
                    break

        if response is None:
            return {"errors": ["Bitquery request was not sent."]}

        if response.status_code >= 400:
            return {"errors": [f"Bitquery HTTP error: {response.status_code}"]}
        try:
            return response.json()
        except ValueError:
            return {"errors": ["Bitquery returned non-JSON response."]}


def _bitquery_header_candidates(api_key: str, endpoint: str) -> list[dict[str, str]]:
    endpoint_lower = endpoint.lower()
    is_v2_endpoint = "streaming.bitquery.io" in endpoint_lower
    looks_like_token = api_key.startswith("ory_at_")
    base_headers = {"Content-Type": "application/json"}

    if is_v2_endpoint or looks_like_token:
        return [
            {**base_headers, "Authorization": f"Bearer {api_key}"},
            {**base_headers, "X-API-KEY": api_key},
        ]

    return [
        {**base_headers, "X-API-KEY": api_key},
        {**base_headers, "Authorization": f"Bearer {api_key}"},
    ]
