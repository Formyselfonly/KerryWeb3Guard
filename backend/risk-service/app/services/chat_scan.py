from app.providers.llm import LLMProvider
from app.schemas.chat import ChatScanRequest, ChatScanResponse


class ChatScanService:
    def __init__(self) -> None:
        self.llm = LLMProvider()

    async def scan(self, request: ChatScanRequest) -> ChatScanResponse:
        payload = {
            "chat_text": request.chat_text,
            "response_language": request.response_language,
        }
        system_prompt = (
            "You are a scam conversation analyst for Web3 users.\n"
            "Reply in response_language. Return JSON with keys:\n"
            "risk_score (0-100 integer), scam_type, summary,\n"
            "evidence_points (array), recommended_action."
        )
        fallback = {
            "risk_score": 55,
            "scam_type": "Unknown (LLM not configured)",
            "summary": "LLM is not configured; this is a placeholder result.",
            "evidence_points": [
                "OPENAI_API_KEY is missing or response parsing failed."
            ],
            "recommended_action": "Do not transfer funds until analysis is ready.",
        }
        result = await self.llm.run_json_analysis(system_prompt, payload, fallback)
        return ChatScanResponse(module="scam_chat_analyzer", **result)
