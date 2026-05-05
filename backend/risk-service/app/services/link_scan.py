from app.providers.llm import LLMProvider
from app.schemas.link import LinkScanRequest, LinkScanResponse


class LinkScanService:
    def __init__(self) -> None:
        self.llm = LLMProvider()

    async def scan(self, request: LinkScanRequest) -> LinkScanResponse:
        payload = {
            "url": request.url,
            "response_language": request.response_language,
            "checks": [
                "domain suspicious patterns",
                "phishing wording",
                "wallet interaction risk",
                "official-brand consistency",
            ],
        }
        system_prompt = (
            "You are a Web3 phishing detection assistant.\n"
            "Reply in response_language. Return JSON with keys:\n"
            "risk_score (0-100 integer), summary, reasons (array), advice."
        )
        fallback = {
            "risk_score": 45,
            "summary": "LLM is not configured; this is a placeholder result.",
            "reasons": [
                "OPENAI_API_KEY is missing or response parsing failed.",
                "Configure .env and retry for full AI analysis.",
            ],
            "advice": "Do not connect wallet until this link is verified.",
        }
        result = await self.llm.run_json_analysis(system_prompt, payload, fallback)
        return LinkScanResponse(module="link_safety_check", **result)
