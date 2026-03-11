import json
from typing import Any

from langchain_openai import ChatOpenAI

from app.core.settings import get_settings


class LLMProvider:
    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.openai_api_key
        self._model_name = settings.openai_model
        self._base_url = settings.openai_base_url

    async def run_json_analysis(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        if not self._api_key:
            return fallback

        llm = ChatOpenAI(
            model=self._model_name,
            api_key=self._api_key,
            base_url=self._base_url,
            temperature=0.1,
        )
        user_prompt = (
            "Return only valid JSON object with required keys.\n"
            f"Input payload:\n{json.dumps(user_payload, ensure_ascii=False)}"
        )
        result = await llm.ainvoke(
            [
                ("system", system_prompt),
                ("user", user_prompt),
            ]
        )
        content = (result.content or "").strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return fallback
