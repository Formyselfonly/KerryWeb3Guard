from typing import Any

from app.core.anti_scam_guide import get_scam_pattern_playbook
from app.providers.llm import LLMProvider
from app.schemas.learn import (
    LearnRequest,
    LearnResponse,
    ScamPatternCard,
    ScamPatternGuideRequest,
    ScamPatternGuideResponse,
)


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

    async def generate_scam_pattern_guide(
        self,
        request: ScamPatternGuideRequest,
    ) -> ScamPatternGuideResponse:
        playbook = get_scam_pattern_playbook(request.response_language)
        default_pattern_id = (
            request.pattern_id or str(playbook[0]["pattern_id"])
            if playbook
            else "last_minute_link_urgency"
        )
        payload: dict[str, Any] = {
            "response_language": request.response_language,
            "user_question": request.user_question or "",
            "selected_pattern_id": request.pattern_id or "",
            "default_pattern_id": default_pattern_id,
            "playbook": playbook,
            "interaction_goal": (
                "Help user learn scam patterns interactively with practical checks."
            ),
        }
        system_prompt = (
            "You are an anti-scam tutor for Web3 users.\n"
            "Reply in response_language.\n"
            "Use playbook as your source of truth for scam patterns.\n"
            "Choose selected_pattern_id by priority:\n"
            "1) If selected_pattern_id exists in playbook, use it.\n"
            "2) Otherwise infer best-matching one from user_question.\n"
            "3) Otherwise use default_pattern_id.\n"
            "Return STRICT JSON with keys:\n"
            "topic (string), intro (string), selected_pattern_id (string),\n"
            "explanation (string), interactive_checklist (string array),\n"
            "next_questions (string array).\n"
            "Requirements:\n"
            "- explanation must include concrete scam flow and defense logic.\n"
            "- interactive_checklist should be actionable yes/no checks.\n"
            "- next_questions must guide user to continue interaction.\n"
            "- Keep tone practical and concise."
        )
        fallback = self._fallback_scam_pattern_guide(
            language=request.response_language,
            playbook=playbook,
            selected_pattern_id=default_pattern_id,
        )
        result = await self.llm.run_json_analysis(system_prompt, payload, fallback)
        normalized = self._normalize_scam_pattern_result(
            result=result,
            fallback=fallback,
            playbook=playbook,
            language=request.response_language,
        )
        return ScamPatternGuideResponse(
            topic=normalized["topic"],
            intro=normalized["intro"],
            pattern_catalog=[ScamPatternCard(**item) for item in playbook],
            selected_pattern_id=normalized["selected_pattern_id"],
            explanation=normalized["explanation"],
            interactive_checklist=normalized["interactive_checklist"],
            next_questions=normalized["next_questions"],
        )

    @staticmethod
    def _fallback_scam_pattern_guide(
        language: str,
        playbook: list[dict[str, Any]],
        selected_pattern_id: str,
    ) -> dict[str, Any]:
        selected = next(
            (item for item in playbook if item["pattern_id"] == selected_pattern_id),
            playbook[0] if playbook else None,
        )
        if selected is None:
            if language == "zh-CN":
                return {
                    "topic": "Web3 求职反诈套路学习",
                    "intro": "当前教学库暂不可用，请稍后重试。",
                    "selected_pattern_id": "unknown",
                    "explanation": "暂无可用套路，请先用 /chat 进行风险分析。",
                    "interactive_checklist": ["是否存在紧迫催促话术？"],
                    "next_questions": ["你现在最担心哪一步？"],
                }
            return {
                "topic": "Web3 job-scam pattern learning",
                "intro": "Pattern library is temporarily unavailable.",
                "selected_pattern_id": "unknown",
                "explanation": "No pattern available now. Use /chat for quick risk check.",
                "interactive_checklist": ["Do you see urgency pressure in the chat?"],
                "next_questions": ["Which step worries you most right now?"],
            }

        name = str(selected["name"])
        scenario = str(selected["scenario"])
        red_flags = [str(item) for item in selected.get("red_flags", [])]
        safe_actions = [str(item) for item in selected.get("safe_actions", [])]

        if language == "zh-CN":
            return {
                "topic": "Web3 求职反诈套路学习",
                "intro": "下面是基于社区经验的互动式骗术学习。",
                "selected_pattern_id": str(selected["pattern_id"]),
                "explanation": (
                    f"当前套路：{name}。\n"
                    f"典型场景：{scenario}\n"
                    "核心逻辑：骗子通过制造时间压力，降低你的核验和判断能力。"
                ),
                "interactive_checklist": (
                    red_flags[:3]
                    + [f"防御动作：{item}" for item in safe_actions[:3]]
                ),
                "next_questions": [
                    "对方是否拒绝使用 Google Meet/Zoom/Lark？",
                    "该链接是否来自官方域名？",
                    "你是否被催促立刻下载未知软件？",
                ],
            }

        return {
            "topic": "Web3 job-scam pattern learning",
            "intro": "Interactive anti-scam lesson based on community playbook.",
            "selected_pattern_id": str(selected["pattern_id"]),
            "explanation": (
                f"Pattern: {name}.\n"
                f"Typical scenario: {scenario}\n"
                "Core logic: scammers create urgency to reduce your verification "
                "quality and push unsafe actions."
            ),
            "interactive_checklist": (
                red_flags[:3] + [f"Defense action: {item}" for item in safe_actions[:3]]
            ),
            "next_questions": [
                "Did they refuse mainstream tools like Meet/Zoom/Lark?",
                "Is the URL from an official domain?",
                "Are you being pushed to install unknown software now?",
            ],
        }

    @staticmethod
    def _normalize_string_list(value: Any, fallback: list[str]) -> list[str]:
        if isinstance(value, list):
            cleaned = [str(item).strip() for item in value if str(item).strip()]
            if cleaned:
                return cleaned[:6]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return fallback[:6]

    @classmethod
    def _normalize_scam_pattern_result(
        cls,
        result: dict[str, Any],
        fallback: dict[str, Any],
        playbook: list[dict[str, Any]],
        language: str,
    ) -> dict[str, Any]:
        available_ids = {str(item["pattern_id"]) for item in playbook}
        selected_pattern_id = str(
            result.get("selected_pattern_id", fallback["selected_pattern_id"])
        )
        if selected_pattern_id not in available_ids:
            selected_pattern_id = str(fallback["selected_pattern_id"])

        topic = str(result.get("topic", fallback["topic"])).strip() or str(
            fallback["topic"]
        )
        intro = str(result.get("intro", fallback["intro"])).strip() or str(
            fallback["intro"]
        )
        explanation = str(
            result.get("explanation", fallback["explanation"])
        ).strip() or str(fallback["explanation"])

        interactive_checklist = cls._normalize_string_list(
            result.get("interactive_checklist"),
            [str(item) for item in fallback["interactive_checklist"]],
        )
        next_questions = cls._normalize_string_list(
            result.get("next_questions"),
            [str(item) for item in fallback["next_questions"]],
        )
        if len(next_questions) < 2:
            next_questions.append(
                "还有哪些细节你希望我继续帮你判断？"
                if language == "zh-CN"
                else "What additional detail do you want me to assess next?"
            )

        return {
            "topic": topic,
            "intro": intro,
            "selected_pattern_id": selected_pattern_id,
            "explanation": explanation,
            "interactive_checklist": interactive_checklist,
            "next_questions": next_questions[:4],
        }
