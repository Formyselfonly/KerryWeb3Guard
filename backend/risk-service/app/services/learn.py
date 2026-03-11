from app.providers.llm import LLMProvider
from app.schemas.learn import LearnRequest, LearnResponse


class LearnService:
    def __init__(self) -> None:
        self.llm = LLMProvider()

    async def generate(self, request: LearnRequest) -> LearnResponse:
        payload = {
            "topic": request.topic or "web3 safety basics",
            "user_question": request.user_question or "",
            "response_language": request.response_language,
        }
        system_prompt = (
            "You are a Web3 beginner educator.\n"
            "Reply in response_language. Return JSON with keys:\n"
            "title, summary, key_points (array), action_checklist (array),\n"
            "quiz_questions (array). Keep concise and beginner-friendly."
        )
        fallback = {
            "title": "Web3 Safety Basics",
            "summary": "LLM is not configured; this is a placeholder lesson.",
            "key_points": [
                "Never share private key or seed phrase.",
                "Always verify links before connecting wallet.",
                "Avoid urgent investment promises.",
            ],
            "action_checklist": [
                "Use a separate wallet for testing.",
                "Double-check domain spelling.",
                "Ask for a second opinion before sending funds.",
            ],
            "quiz_questions": ["Why should you never share a seed phrase?"],
        }
        result = await self.llm.run_json_analysis(system_prompt, payload, fallback)
        return LearnResponse(**result)
