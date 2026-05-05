from urllib.parse import urlparse

from app.providers.llm import LLMProvider
from app.schemas.link import LinkScanRequest, LinkScanResponse


class LinkScanService:
    def __init__(self) -> None:
        self.llm = LLMProvider()

    async def scan(self, request: LinkScanRequest) -> LinkScanResponse:
        analysis = self._extract_link_signals(request.url)
        payload = {
            "url": request.url,
            "response_language": request.response_language,
            "feature_name": "interview_link_safety_scan_analysis",
            "signals": analysis,
            "required_focus": [
                "Check whether URL belongs to mainstream meeting ecosystems: "
                "Zoom / Google Meet / Lark / Teams.",
                "If not mainstream, treat as high-risk signal.",
                "If software download is required, user should manually download "
                "from official channels, not from interview URL.",
                "Check whether URL format is valid and suspicious.",
                "Return clear conclusion and evidence.",
            ],
        }
        system_prompt = (
            "You are an interview link safety analyst for Web3 anti-scam scenarios.\n"
            "Reply in response_language.\n"
            "Use provided signals and rules, but make final judgment with balanced "
            "reasoning.\n"
            "Output STRICT JSON object with keys:\n"
            "risk_score (0-100 integer), summary (string), reasons (string array), "
            "advice (string).\n"
            "Scoring guidance:\n"
            "- If domain is not mainstream meeting ecosystem, treat as strong risk.\n"
            "- If URL appears to push software download from non-official source, "
            "raise risk sharply.\n"
            "- Invalid URL format, non-HTTPS, punycode, raw-IP host are additional "
            "risk signals.\n"
            "In summary/advice, explicitly mention conclusion and concrete next steps."
        )
        fallback = self._fallback_response(request.response_language, analysis)
        result = await self.llm.run_json_analysis(system_prompt, payload, fallback)
        normalized = self._normalize_llm_result(result, fallback)

        return LinkScanResponse(
            module="interview_link_safety_scan_analysis",
            **normalized,
        )

    @staticmethod
    def _is_subdomain_of(host: str, domain: str) -> bool:
        return host == domain or host.endswith(f".{domain}")

    @classmethod
    def _extract_link_signals(cls, raw_url: str) -> dict[str, str | bool]:
        url = raw_url.strip()
        parsed = urlparse(url)
        host = parsed.netloc.lower().split(":")[0]
        path = parsed.path.lower()
        query = parsed.query.lower()

        mainstream_domains = (
            "zoom.us",
            "meet.google.com",
            "larksuite.com",
            "feishu.cn",
            "teams.microsoft.com",
            "teams.live.com",
        )
        official_download_domains = (
            "zoom.us",
            "zoom.com",
            "google.com",
            "microsoft.com",
            "larksuite.com",
            "feishu.cn",
            "apple.com",
            "play.google.com",
            "apps.microsoft.com",
        )
        download_keywords = (
            "download",
            "installer",
            "setup",
            "client",
            "apk",
            "dmg",
            "exe",
            "msi",
            "pkg",
            "zip",
        )
        suspicious_extensions = (
            ".exe",
            ".msi",
            ".bat",
            ".scr",
            ".dmg",
            ".apk",
            ".pkg",
            ".zip",
            ".rar",
            ".7z",
        )

        format_valid = bool(
            parsed.scheme in {"http", "https"}
            and host
            and " " not in url
            and "." in host
        )
        is_https = parsed.scheme == "https"
        host_is_ip = host.replace(".", "").isdigit()
        has_punycode = "xn--" in host
        is_mainstream_meeting = any(
            cls._is_subdomain_of(host, domain) for domain in mainstream_domains
        )
        looks_like_download = any(
            token in path or token in query for token in download_keywords
        )
        has_suspicious_extension = any(
            path.endswith(ext) or f"{ext}?" in f"{path}?{query}"
            for ext in suspicious_extensions
        )
        official_download_source = any(
            cls._is_subdomain_of(host, domain) for domain in official_download_domains
        )

        return {
            "url": url,
            "host": host,
            "format_valid": format_valid,
            "is_https": is_https,
            "host_is_ip": host_is_ip,
            "has_punycode": has_punycode,
            "is_mainstream_meeting": is_mainstream_meeting,
            "looks_like_download": looks_like_download,
            "has_suspicious_extension": has_suspicious_extension,
            "official_download_source": official_download_source,
        }

    @staticmethod
    def _baseline_score(analysis: dict[str, str | bool]) -> int:
        score = 20
        if not analysis["format_valid"]:
            score += 45
        if not analysis["is_mainstream_meeting"]:
            score += 35
        if not analysis["is_https"]:
            score += 10
        if analysis["looks_like_download"]:
            score += 15
        if analysis["has_suspicious_extension"]:
            score += 20
        if analysis["host_is_ip"]:
            score += 15
        if analysis["has_punycode"]:
            score += 10
        if analysis["looks_like_download"] and not analysis["official_download_source"]:
            score += 15
        return max(0, min(100, score))

    @staticmethod
    def _fallback_response(
        language: str,
        analysis: dict[str, str | bool],
    ) -> dict[str, int | str | list[str]]:
        baseline = LinkScanService._baseline_score(analysis)
        host = str(analysis["host"]) or "N/A"
        if language == "zh-CN":
            return {
                "risk_score": baseline,
                "summary": (
                    f"已完成面试链接基础检查（域名：{host}）。当前为规则兜底结论，"
                    "建议谨慎核验后再继续。"
                ),
                "reasons": [
                    "本次结果使用规则兜底（AI不可用或返回异常）。",
                    (
                        "主流会议域名检查：通过"
                        if analysis["is_mainstream_meeting"]
                        else "主流会议域名检查：未通过（高风险信号）。"
                    ),
                    (
                        "链接格式检查：通过"
                        if analysis["format_valid"]
                        else "链接格式检查：异常。"
                    ),
                ],
                "advice": (
                    "不要通过面试链接下载软件。若必须下载，请自行访问官方渠道；并"
                    "核验招聘方身份。"
                ),
            }

        return {
            "risk_score": baseline,
            "summary": (
                f"Interview-link baseline scan completed (domain: {host}). This is "
                "a fallback result; verify manually before proceeding."
            ),
            "reasons": [
                "Fallback rule-based output used (AI unavailable or malformed).",
                (
                    "Mainstream meeting-domain check: passed."
                    if analysis["is_mainstream_meeting"]
                    else "Mainstream meeting-domain check: failed (high-risk signal)."
                ),
                (
                    "URL format check: passed."
                    if analysis["format_valid"]
                    else "URL format check: invalid."
                ),
            ],
            "advice": (
                "Do not install software from interview URLs. If required, use "
                "official download channels and verify recruiter identity first."
            ),
        }

    @staticmethod
    def _normalize_llm_result(
        result: dict,
        fallback: dict[str, int | str | list[str]],
    ) -> dict[str, int | str | list[str]]:
        score_raw = result.get("risk_score", fallback["risk_score"])
        try:
            risk_score = int(score_raw)
        except (TypeError, ValueError):
            risk_score = int(fallback["risk_score"])
        risk_score = max(0, min(100, risk_score))

        summary_raw = result.get("summary", fallback["summary"])
        summary = summary_raw if isinstance(summary_raw, str) else str(summary_raw)
        if not summary.strip():
            summary = str(fallback["summary"])

        reasons_raw = result.get("reasons", fallback["reasons"])
        if isinstance(reasons_raw, list):
            reasons = [str(item) for item in reasons_raw if str(item).strip()]
        elif isinstance(reasons_raw, str):
            reasons = [reasons_raw]
        else:
            reasons = [str(item) for item in fallback["reasons"]]
        if not reasons:
            reasons = [str(item) for item in fallback["reasons"]]

        advice_raw = result.get("advice", fallback["advice"])
        if isinstance(advice_raw, list):
            advice = " ".join(str(item) for item in advice_raw if item is not None)
        elif isinstance(advice_raw, str):
            advice = advice_raw
        else:
            advice = str(advice_raw)
        if not advice.strip():
            advice = str(fallback["advice"])

        return {
            "risk_score": risk_score,
            "summary": summary,
            "reasons": reasons[:8],
            "advice": advice,
        }
