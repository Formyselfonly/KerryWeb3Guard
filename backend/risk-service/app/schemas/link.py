import ipaddress
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import BaseScanResponse, Language


class LinkScanRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    response_language: Language = "en"

    @field_validator("url")
    @classmethod
    def validate_url_security(cls, value: str) -> str:
        url = value.strip()
        parsed = urlparse(url)
        scheme = (parsed.scheme or "").lower()
        host = (parsed.hostname or "").strip().lower()

        if scheme not in {"http", "https"}:
            raise ValueError("Only http/https URLs are allowed.")
        if not host:
            raise ValueError("URL host is required.")

        blocked_hostnames = {
            "localhost",
            "metadata.google.internal",
            "169.254.169.254",
        }
        if (
            host in blocked_hostnames
            or host.endswith(".localhost")
            or host.endswith(".local")
            or host.endswith(".localdomain")
        ):
            raise ValueError("Local/internal hosts are not allowed.")

        ip_literal: ipaddress.IPv4Address | ipaddress.IPv6Address | None = None
        try:
            ip_literal = ipaddress.ip_address(host)
        except ValueError:
            ip_literal = None
        if ip_literal is not None and (
            ip_literal.is_private
            or ip_literal.is_loopback
            or ip_literal.is_link_local
            or ip_literal.is_multicast
            or ip_literal.is_reserved
            or ip_literal.is_unspecified
        ):
            raise ValueError("Private/internal IP targets are not allowed.")

        return url


class LinkScanResponse(BaseScanResponse):
    reasons: list[str]
    advice: str
