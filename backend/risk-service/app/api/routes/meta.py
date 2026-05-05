import httpx
from fastapi import APIRouter

from app.core.settings import get_settings
from app.schemas.meta import KeyCheckResult, KeyVerificationResponse

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/chains", response_model=list[str])
async def get_supported_chains() -> list[str]:
    settings = get_settings()
    return [
        item.strip()
        for item in settings.dexscreener_supported_chains.split(",")
        if item.strip()
    ]


@router.get("/verify-keys", response_model=KeyVerificationResponse)
async def verify_keys() -> KeyVerificationResponse:
    settings = get_settings()
    openai_result = await _verify_openai_key(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )
    bitquery_result = await _verify_bitquery_key(
        api_key=settings.bitquery_api_key,
        endpoint=settings.bitquery_endpoint,
    )
    return KeyVerificationResponse(
        openai=openai_result,
        bitquery=bitquery_result,
    )


async def _verify_openai_key(api_key: str, base_url: str) -> KeyCheckResult:
    if not api_key:
        return KeyCheckResult(
            configured=False,
            valid=False,
            message="OPENAI_API_KEY is not configured.",
        )

    url = f"{base_url.rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
        if response.status_code == 200:
            return KeyCheckResult(
                configured=True,
                valid=True,
                message="OpenAI-compatible key is valid.",
            )
        return KeyCheckResult(
            configured=True,
            valid=False,
            message=f"OpenAI key check failed: HTTP {response.status_code}.",
        )
    except Exception as exc:  # pragma: no cover - defensive network handling
        return KeyCheckResult(
            configured=True,
            valid=False,
            message=f"OpenAI key check error: {exc}",
        )


async def _verify_bitquery_key(api_key: str, endpoint: str) -> KeyCheckResult:
    if not api_key:
        return KeyCheckResult(
            configured=False,
            valid=False,
            message="BITQUERY_API_KEY is not configured.",
        )

    # Introspection-style minimal query to validate auth regardless schema details.
    payload = {"query": "query VerifyBitquery { __typename }", "variables": {}}
    header_candidates = _bitquery_header_candidates(api_key=api_key, endpoint=endpoint)

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response: httpx.Response | None = None
            for headers in header_candidates:
                response = await client.post(endpoint, json=payload, headers=headers)
                if response.status_code not in (401, 403):
                    break

        if response is None:
            return KeyCheckResult(
                configured=True,
                valid=False,
                message="Bitquery key check failed: request not sent.",
            )

        if response.status_code != 200:
            return KeyCheckResult(
                configured=True,
                valid=False,
                message=f"Bitquery key check failed: HTTP {response.status_code}.",
            )

        data = response.json()
        if data.get("errors"):
            first_error = data["errors"][0]
            if isinstance(first_error, dict):
                detail = first_error.get("message", str(first_error))
            else:
                detail = str(first_error)
            auth_error_keywords = ("unauthorized", "forbidden", "invalid token")
            if any(keyword in detail.lower() for keyword in auth_error_keywords):
                return KeyCheckResult(
                    configured=True,
                    valid=False,
                    message=f"Bitquery key check failed: {detail}",
                )
            return KeyCheckResult(
                configured=True,
                valid=True,
                message=(
                    "Bitquery token is accepted, but query returned schema "
                    f"errors: {detail}"
                ),
            )

        return KeyCheckResult(
            configured=True,
            valid=True,
            message="Bitquery key is valid.",
        )
    except Exception as exc:  # pragma: no cover - defensive network handling
        return KeyCheckResult(
            configured=True,
            valid=False,
            message=f"Bitquery key check error: {exc}",
        )


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
