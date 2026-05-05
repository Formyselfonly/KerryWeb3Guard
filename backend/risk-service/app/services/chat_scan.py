from app.core.anti_scam_guide import detect_scam_rules
from app.providers.llm import LLMProvider
from app.schemas.chat import ChatScanRequest, ChatScanResponse


class ChatScanService:
    def __init__(self) -> None:
        self.llm = LLMProvider()

    async def scan(self, request: ChatScanRequest) -> ChatScanResponse:
        rule_hits = detect_scam_rules(
            chat_text=request.chat_text,
            language=request.response_language,
        )
        payload = {
            "chat_text": request.chat_text,
            "response_language": request.response_language,
            "rule_hits": rule_hits,
        }
        system_prompt = (
            "You are a scam conversation analyst for Web3 users.\n"
            "Use rule_hits as risk evidence only when they truly match context.\n"
            "Scoring rubric:\n"
            "- 0-35: low risk (no concrete malicious indicator).\n"
            "- 36-65: medium risk (ambiguous social engineering signs).\n"
            "- 66-85: high risk (explicit unknown software install, remote "
            "control, or sensitive data request).\n"
            "- 86-100: critical risk (seed phrase/private key/asset transfer/"
            "credential theft intent).\n"
            "If text only mentions meeting software or screen sharing but does "
            "not specify unknown source/non-mainstream tool/sensitive-data "
            "request, keep risk_score <= 65 and ask for verification steps.\n"
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
        normalized = self._normalize_llm_result(result, fallback, rule_hits)
        normalized = self._apply_risk_calibration(
            chat_text=request.chat_text,
            language=request.response_language,
            result=normalized,
        )
        return ChatScanResponse(module="scam_chat_analyzer", **normalized)

    @staticmethod
    def _normalize_llm_result(
        result: dict,
        fallback: dict,
        rule_hits: list[str],
    ) -> dict:
        score_raw = result.get("risk_score", fallback["risk_score"])
        try:
            risk_score = int(score_raw)
        except (TypeError, ValueError):
            risk_score = int(fallback["risk_score"])
        risk_score = max(0, min(100, risk_score))

        scam_type_raw = result.get("scam_type", fallback["scam_type"])
        scam_type = scam_type_raw if isinstance(scam_type_raw, str) else str(scam_type_raw)

        summary_raw = result.get("summary", fallback["summary"])
        summary = summary_raw if isinstance(summary_raw, str) else str(summary_raw)

        evidence_raw = result.get("evidence_points", fallback["evidence_points"])
        if isinstance(evidence_raw, list):
            evidence_points = [str(item) for item in evidence_raw]
        elif isinstance(evidence_raw, str):
            evidence_points = [evidence_raw]
        else:
            evidence_points = [str(item) for item in fallback["evidence_points"]]

        for hit in rule_hits:
            marker = f"Rule matched: {hit}"
            if marker not in evidence_points:
                evidence_points.append(marker)

        advice_raw = result.get("recommended_action", fallback["recommended_action"])
        if isinstance(advice_raw, list):
            recommended_action = " ".join(
                str(item) for item in advice_raw if item is not None
            )
        elif isinstance(advice_raw, str):
            recommended_action = advice_raw
        else:
            recommended_action = str(advice_raw)

        if not recommended_action.strip():
            recommended_action = fallback["recommended_action"]

        return {
            "risk_score": risk_score,
            "scam_type": scam_type,
            "summary": summary,
            "evidence_points": evidence_points,
            "recommended_action": recommended_action,
        }

    @staticmethod
    def _contains_any(content: str, keywords: tuple[str, ...]) -> bool:
        return any(keyword in content for keyword in keywords)

    @classmethod
    def _apply_risk_calibration(
        cls,
        chat_text: str,
        language: str,
        result: dict,
    ) -> dict:
        content = chat_text.lower()

        meeting_or_share_keywords = (
            "会议软件",
            "开屏幕",
            "屏幕共享",
            "共享屏幕",
            "meeting app",
            "meeting software",
            "screen share",
            "share screen",
            "remote meeting",
            "download",
            "下载安装",
            "下载",
            "安装",
        )
        high_confidence_keywords = (
            "非主流",
            "未知来源",
            "奇怪软件",
            "远程控制",
            "验证码",
            "银行卡",
            "身份证",
            "助记词",
            "私钥",
            "转账",
            ".exe",
            ".scr",
            ".bat",
            "unknown source",
            "non-mainstream",
            "remote control",
            "otp",
            "bank card",
            "id card",
            "seed phrase",
            "private key",
            "wire transfer",
            "send funds",
        )
        mainstream_tool_keywords = (
            "zoom",
            "google meet",
            "lark",
            "microsoft teams",
            "teams",
        )

        mentions_meeting_flow = cls._contains_any(content, meeting_or_share_keywords)
        has_high_confidence_signals = cls._contains_any(
            content, high_confidence_keywords
        )
        mentions_mainstream_tools = cls._contains_any(
            content, mainstream_tool_keywords
        )

        risk_score = int(result["risk_score"])
        evidence_points = list(result["evidence_points"])
        summary = str(result["summary"])
        recommended_action = str(result["recommended_action"])

        if mentions_meeting_flow and not has_high_confidence_signals:
            if risk_score > 65:
                risk_score = 65
            if language == "zh-CN":
                marker = (
                    "仅出现“会议软件/屏幕共享”描述，未见未知来源、敏感信息"
                    "索取或资产操作等硬性高危证据。"
                )
                if marker not in evidence_points:
                    evidence_points.append(marker)
                if "需补充信息" not in summary:
                    summary = (
                        f"{summary} 当前更接近中等风险，需补充信息后再提升风险"
                        "等级。"
                    )
                recommended_action = (
                    f"{recommended_action} 请先确认会议软件名称、下载来源"
                    "（官网/应用商店）以及是否涉及远程控制权限。"
                )
            else:
                marker = (
                    "Only generic meeting software/screen sharing signals are "
                    "present; no hard high-risk indicator detected."
                )
                if marker not in evidence_points:
                    evidence_points.append(marker)
                if "need more context" not in summary.lower():
                    summary = (
                        f"{summary} This is currently medium risk and needs more "
                        "context before escalation."
                    )
                recommended_action = (
                    f"{recommended_action} Verify software name, official download "
                    "source, and whether remote control permissions are required."
                )

        if mentions_mainstream_tools and not has_high_confidence_signals:
            risk_score = min(risk_score, 45)

        result["risk_score"] = max(0, min(100, risk_score))
        result["evidence_points"] = evidence_points
        result["summary"] = summary
        result["recommended_action"] = recommended_action
        return result
