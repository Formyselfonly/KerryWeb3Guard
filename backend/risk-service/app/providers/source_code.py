from typing import Any

import httpx

EVM_CHAIN_ID_BY_SLUG: dict[str, int] = {
    "ethereum": 1,
    "bsc": 56,
    "polygon": 137,
    "arbitrum": 42161,
    "optimism": 10,
    "base": 8453,
    "avalanche": 43114,
    "fantom": 250,
    "linea": 59144,
    "blast": 81457,
    "zksync": 324,
    "mantle": 5000,
    "scroll": 534352,
    "sei": 1329,
}

EXPLORER_BASE_BY_SLUG: dict[str, str] = {
    "ethereum": "https://etherscan.io/address",
    "bsc": "https://bscscan.com/address",
    "polygon": "https://polygonscan.com/address",
    "arbitrum": "https://arbiscan.io/address",
    "optimism": "https://optimistic.etherscan.io/address",
    "base": "https://basescan.org/address",
    "avalanche": "https://snowtrace.io/address",
    "fantom": "https://ftmscan.com/address",
    "linea": "https://lineascan.build/address",
    "blast": "https://blastscan.io/address",
    "zksync": "https://era.zksync.network/address",
    "mantle": "https://mantlescan.xyz/address",
    "scroll": "https://scrollscan.com/address",
    "sei": "https://seistream.app/address",
}


class SourceCodeProvider:
    async def check_contract_source(
        self,
        chain: str,
        contract_address: str,
    ) -> dict[str, Any]:
        explorer_base = EXPLORER_BASE_BY_SLUG.get(chain)
        check_url = (
            f"{explorer_base}/{contract_address}#code"
            if explorer_base
            else None
        )
        chain_id = EVM_CHAIN_ID_BY_SLUG.get(chain)
        if not chain_id:
            return {
                "is_public": None,
                "status": "unknown",
                "source_platform": "explorer",
                "check_url": check_url,
                "note": "Source verification is unsupported for this chain.",
            }

        full_url = (
            "https://repo.sourcify.dev/contracts/full_match/"
            f"{chain_id}/{contract_address}/metadata.json"
        )
        partial_url = (
            "https://repo.sourcify.dev/contracts/partial_match/"
            f"{chain_id}/{contract_address}/metadata.json"
        )
        async with httpx.AsyncClient(timeout=10.0) as client:
            full_response = await client.get(full_url)
            if full_response.status_code == 200:
                return {
                    "is_public": True,
                    "status": "verified",
                    "source_platform": "sourcify_full_match",
                    "check_url": check_url,
                    "note": "Verified in Sourcify full match registry.",
                }

            partial_response = await client.get(partial_url)
            if partial_response.status_code == 200:
                return {
                    "is_public": True,
                    "status": "verified",
                    "source_platform": "sourcify_partial_match",
                    "check_url": check_url,
                    "note": "Verified in Sourcify partial match registry.",
                }

        return {
            "is_public": False,
            "status": "unverified",
            "source_platform": "sourcify",
            "check_url": check_url,
            "note": "No verified source record found in Sourcify.",
        }
