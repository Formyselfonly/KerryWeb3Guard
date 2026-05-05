from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path
import re
import time
from typing import Any

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict
from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    Update,
)
from telegram.error import BadRequest, NetworkError, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    telegram_bot_token: str
    api_base_url: str = "http://127.0.0.1:8000"
    default_response_language: str = "zh-CN"
    backend_http_timeout_seconds: float = 30.0
    backend_max_connections: int = 50
    backend_max_keepalive_connections: int = 10
    backend_keepalive_expiry_seconds: float = 20.0
    free_command_cooldown_seconds: float = 1.0
    usage_log_path: str = "logs/telegram-usage.log"
    initial_quota_points: int = 5
    daily_quota_base: int = 3
    checkin_bonus_quota: int = 5
    invite_bonus_quota: int = 20
    cost_link_scan: int = 1
    cost_chat_scan: int = 2
    cost_contract_scan: int = 5
    cost_learn_scam: int = 1
    log_full_io: bool = False
    log_full_io_max_chars: int = 4000
    quota_timezone_offset_hours: int = 8
    quota_state_path: str = "logs/quota-state.json"
    overload_mode_enabled: bool = False
    overload_mode_message: str = "当前请求较多，系统正在排队处理中，请稍后再试。"


LANG_CALLBACK_PREFIX = "lang:"
SCAM_CALLBACK_PREFIX = "scam:"
START_VIEW_CALLBACK_PREFIX = "startview:"
SCAM_MODE_KEY = "learn_scam_active"
SCAM_PATTERN_KEY = "learn_scam_pattern_id"
USAGE_LOGGER_KEY = "usage_logger"
QUOTA_MANAGER_KEY = "quota_manager"
FREE_CMD_COOLDOWN_TS_KEY = "free_cmd_cooldown_ts"
SCAM_PLAYBOOK_CATALOG_ZH: tuple[dict[str, str], ...] = (
    {"pattern_id": "last_minute_link_urgency", "name": "卡点发链接 + 制造紧迫感"},
    {"pattern_id": "non_mainstream_meeting_software", "name": "要求安装非主流会议软件"},
    {"pattern_id": "resume_overmatch_bait", "name": "JD 99% 匹配诱导"},
    {"pattern_id": "unsolicited_dm_job_offer", "name": "陌生私信工作机会"},
    {
        "pattern_id": "code_task_trojan_loader",
        "name": "代码作业投毒（伪装 cache/log + curl 拉取）",
    },
)
SCAM_PLAYBOOK_CATALOG_EN: tuple[dict[str, str], ...] = (
    {
        "pattern_id": "last_minute_link_urgency",
        "name": "Last-minute link + urgency pressure",
    },
    {
        "pattern_id": "non_mainstream_meeting_software",
        "name": "Forced install of unknown meeting app",
    },
    {"pattern_id": "resume_overmatch_bait", "name": "JD 99% perfect-match bait"},
    {"pattern_id": "unsolicited_dm_job_offer", "name": "Unsolicited DM job offer"},
    {
        "pattern_id": "code_task_trojan_loader",
        "name": "Code-task malware loader (fake cache/log + curl fetch)",
    },
)


def _setup_usage_logger(settings: Settings) -> logging.Logger:
    logger = logging.getLogger("kerryweb3guard.usage")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    log_path = Path(settings.usage_log_path).expanduser()
    if not log_path.is_absolute():
        log_path = Path(__file__).resolve().parent / log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter("%(asctime)s %(message)s")
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


def _truncate_text(value: str, max_chars: int = 160) -> str:
    content = value.strip()
    if len(content) <= max_chars:
        return content
    return f"{content[:max_chars]}..."


def _log_text(
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    default_max_chars: int = 160,
) -> str:
    settings = context.application.bot_data.get("settings")
    if isinstance(settings, Settings) and settings.log_full_io:
        max_chars = max(256, int(settings.log_full_io_max_chars))
        return _truncate_text(text, max_chars=max_chars)
    return _truncate_text(text, max_chars=default_max_chars)


def _extract_actor(update: Update) -> dict[str, Any]:
    user = update.effective_user
    chat = update.effective_chat
    return {
        "user_id": user.id if user else None,
        "username": user.username if user and user.username else None,
        "chat_id": chat.id if chat else None,
        "chat_type": chat.type if chat else None,
    }


def _log_usage(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    action: str,
    status: str,
    details: dict[str, Any] | None = None,
    started_at: float | None = None,
) -> None:
    logger = context.application.bot_data.get(USAGE_LOGGER_KEY)
    if not isinstance(logger, logging.Logger):
        return

    actor = _extract_actor(update)
    user_id = actor.get("user_id")
    username = actor.get("username")
    if isinstance(user_id, int):
        manager = _get_quota_manager(context)
        if manager is not None:
            manager.sync_user_profile(user_id=user_id, username=username)

    payload: dict[str, Any] = {
        "event": "bot_usage",
        "action": action,
        "status": status,
        **actor,
    }
    if started_at is not None:
        payload["duration_ms"] = round((time.perf_counter() - started_at) * 1000, 1)
    if details:
        payload["details"] = details

    logger.info(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def _check_free_command_cooldown(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    action: str,
) -> bool:
    settings = context.application.bot_data.get("settings")
    cooldown_seconds = 1.0
    if isinstance(settings, Settings):
        cooldown_seconds = max(0.0, float(settings.free_command_cooldown_seconds))
    if cooldown_seconds <= 0:
        return False

    now = time.monotonic()
    user_state = context.user_data.setdefault(FREE_CMD_COOLDOWN_TS_KEY, {})
    if not isinstance(user_state, dict):
        user_state = {}
        context.user_data[FREE_CMD_COOLDOWN_TS_KEY] = user_state

    last_ts = user_state.get(action)
    if isinstance(last_ts, (int, float)) and (now - float(last_ts)) < cooldown_seconds:
        _log_usage(
            update,
            context,
            action=action,
            status="cooldown",
            details={"cooldown_seconds": cooldown_seconds},
        )
        return True

    user_state[action] = now
    return False


class QuotaManager:
    def __init__(
        self,
        state_path: Path,
        initial_points: int,
        daily_base: int,
        checkin_bonus: int,
        invite_bonus: int,
        timezone_offset_hours: int,
    ) -> None:
        self._state_path = state_path
        self._initial_points = max(0, int(initial_points))
        self._daily_base = max(0, int(daily_base))
        self._checkin_bonus = max(0, int(checkin_bonus))
        self._invite_bonus = max(0, int(invite_bonus))
        self._tz = timezone(timedelta(hours=timezone_offset_hours))
        self._state: dict[str, dict[str, Any]] = {"users": {}}
        self._load()

    def _today(self) -> str:
        return datetime.now(self._tz).date().isoformat()

    def _load(self) -> None:
        if not self._state_path.exists():
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            self._save()
            return
        try:
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("users"), dict):
                self._state = payload
        except Exception:
            self._state = {"users": {}}
            self._save()

    def _save(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(
            json.dumps(self._state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _invite_code_for(user_id: int) -> str:
        return f"u{user_id}"

    @staticmethod
    def _user_id_from_invite_code(code: str) -> int | None:
        if not code.startswith("u"):
            return None
        raw = code[1:]
        if not raw.isdigit():
            return None
        return int(raw)

    def _ensure_user(self, user_id: int) -> dict[str, Any]:
        today = self._today()
        users = self._state.setdefault("users", {})
        record = users.get(str(user_id))
        if not isinstance(record, dict):
            record = {
                "balance": self._initial_points,
                "last_daily_grant_date": "",
                "last_checkin_date": "",
                "invite_code": self._invite_code_for(user_id),
                "username_snapshot": "",
                "invited_by": None,
                "invite_reward_granted": False,
                "invite_count": 0,
                "lifetime_used": 0,
            }
        # Legacy migration from old quota model {date, used, bonus, checked_in_date}.
        if "balance" not in record and (
            "used" in record or "bonus" in record or "date" in record
        ):
            legacy_used = max(0, int(record.get("used", 0)))
            legacy_bonus = max(0, int(record.get("bonus", 0)))
            record["balance"] = max(0, self._daily_base + legacy_bonus - legacy_used)
            record["last_daily_grant_date"] = str(record.get("date", ""))
            record["last_checkin_date"] = str(record.get("checked_in_date", ""))
            record["invite_code"] = self._invite_code_for(user_id)
            record["username_snapshot"] = str(record.get("username_snapshot", ""))
            record["invited_by"] = None
            record["invite_reward_granted"] = False
            record["invite_count"] = 0
            record["lifetime_used"] = legacy_used

        record["balance"] = max(0, int(record.get("balance", 0)))
        record["last_daily_grant_date"] = str(record.get("last_daily_grant_date", ""))
        record["last_checkin_date"] = str(record.get("last_checkin_date", ""))
        record["invite_code"] = str(
            record.get("invite_code", self._invite_code_for(user_id))
        )
        record["username_snapshot"] = str(record.get("username_snapshot", ""))
        invited_by_raw = record.get("invited_by")
        record["invited_by"] = (
            int(invited_by_raw)
            if isinstance(invited_by_raw, int) or str(invited_by_raw).isdigit()
            else None
        )
        record["invite_reward_granted"] = bool(record.get("invite_reward_granted", False))
        record["invite_count"] = max(0, int(record.get("invite_count", 0)))
        record["lifetime_used"] = max(0, int(record.get("lifetime_used", 0)))

        # Daily quota accumulates (does not reset previous balance).
        if not record["last_daily_grant_date"]:
            record["last_daily_grant_date"] = today
        elif record["last_daily_grant_date"] != today:
            record["balance"] += self._daily_base
            record["last_daily_grant_date"] = today
        users[str(user_id)] = record
        self._save()
        return record

    def sync_user_profile(self, user_id: int, username: str | None) -> None:
        record = self._ensure_user(user_id)
        clean_username = username.strip() if isinstance(username, str) else ""
        if clean_username and record.get("username_snapshot") != clean_username:
            record["username_snapshot"] = clean_username
            self._save()

    def get_status(self, user_id: int) -> dict[str, int | str | bool]:
        record = self._ensure_user(user_id)
        today = self._today()
        checked_in_today = str(record.get("last_checkin_date", "")) == today
        return {
            "date": today,
            "balance": max(0, int(record["balance"])),
            "lifetime_used": max(0, int(record["lifetime_used"])),
            "initial_quota": self._initial_points,
            "base_quota": self._daily_base,
            "checked_in_today": checked_in_today,
            "checkin_bonus_quota": self._checkin_bonus,
            "invite_bonus_quota": self._invite_bonus,
            "invite_code": str(record.get("invite_code", self._invite_code_for(user_id))),
            "invite_count": max(0, int(record.get("invite_count", 0))),
            "invited_by": record.get("invited_by"),
        }

    def consume(self, user_id: int, amount: int = 1) -> dict[str, int | str | bool]:
        amount = max(1, int(amount))
        record = self._ensure_user(user_id)
        if int(record["balance"]) < amount:
            return self.get_status(user_id)
        record["balance"] = int(record["balance"]) - amount
        record["lifetime_used"] = int(record.get("lifetime_used", 0)) + amount
        self._save()
        return self.get_status(user_id)

    def check_in(self, user_id: int) -> tuple[bool, dict[str, int | str | bool]]:
        record = self._ensure_user(user_id)
        today = self._today()
        if str(record.get("last_checkin_date", "")) == today:
            return False, self.get_status(user_id)
        record["balance"] = int(record.get("balance", 0)) + self._checkin_bonus
        record["last_checkin_date"] = today
        self._save()
        return True, self.get_status(user_id)

    def get_invite_code(self, user_id: int) -> str:
        record = self._ensure_user(user_id)
        code = str(record.get("invite_code", self._invite_code_for(user_id)))
        if not code:
            code = self._invite_code_for(user_id)
            record["invite_code"] = code
            self._save()
        return code

    def bind_inviter(self, user_id: int, invite_code: str) -> str:
        invite_code = invite_code.strip()
        inviter_id = self._user_id_from_invite_code(invite_code)
        if inviter_id is None:
            return "invalid_code"
        if inviter_id == user_id:
            return "self_invite"

        user_record = self._ensure_user(user_id)
        if user_record.get("invited_by") is not None:
            return "already_bound"

        inviter_record = self._ensure_user(inviter_id)
        if not inviter_record:
            return "invalid_code"

        user_record["invited_by"] = inviter_id
        self._save()
        return "bound"

    def apply_invite_reward_on_first_success(
        self,
        user_id: int,
    ) -> dict[str, int | bool]:
        user_record = self._ensure_user(user_id)
        invited_by = user_record.get("invited_by")
        reward_granted = bool(user_record.get("invite_reward_granted", False))
        if invited_by is None or reward_granted:
            return {"applied": False, "inviter_id": 0, "reward": 0}

        inviter_id = int(invited_by)
        inviter_record = self._ensure_user(inviter_id)
        user_record["balance"] = int(user_record.get("balance", 0)) + self._invite_bonus
        user_record["invite_reward_granted"] = True
        inviter_record["balance"] = int(inviter_record.get("balance", 0)) + self._invite_bonus
        inviter_record["invite_count"] = int(inviter_record.get("invite_count", 0)) + 1
        self._save()
        return {"applied": True, "inviter_id": inviter_id, "reward": self._invite_bonus}


def _setup_quota_manager(settings: Settings) -> QuotaManager:
    state_path = Path(settings.quota_state_path).expanduser()
    if not state_path.is_absolute():
        state_path = Path(__file__).resolve().parent / state_path
    return QuotaManager(
        state_path=state_path,
        initial_points=settings.initial_quota_points,
        daily_base=settings.daily_quota_base,
        checkin_bonus=settings.checkin_bonus_quota,
        invite_bonus=settings.invite_bonus_quota,
        timezone_offset_hours=settings.quota_timezone_offset_hours,
    )


@dataclass
class BackendAPIError(Exception):
    status_code: int
    detail: str


@dataclass
class BackendClient:
    base_url: str
    timeout_seconds: float = 30.0
    max_connections: int = 50
    max_keepalive_connections: int = 10
    keepalive_expiry_seconds: float = 20.0

    def __post_init__(self) -> None:
        # Reuse one HTTP client to keep connections warm.
        limits = httpx.Limits(
            max_connections=max(1, int(self.max_connections)),
            max_keepalive_connections=max(1, int(self.max_keepalive_connections)),
            keepalive_expiry=max(1.0, float(self.keepalive_expiry_seconds)),
        )
        self._client = httpx.AsyncClient(timeout=self.timeout_seconds, limits=limits)

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}{path}"
        response = await self._client.get(url, params=params)
        if response.status_code >= 400:
            detail = response.text
            try:
                data = response.json()
                if isinstance(data, dict) and "detail" in data:
                    detail = str(data["detail"])
            except ValueError:
                pass
            raise BackendAPIError(status_code=response.status_code, detail=detail)
        return response.json()

    async def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}{path}"
        response = await self._client.post(url, json=payload)
        if response.status_code >= 400:
            detail = response.text
            try:
                data = response.json()
                if isinstance(data, dict) and "detail" in data:
                    detail = str(data["detail"])
            except ValueError:
                pass
            raise BackendAPIError(status_code=response.status_code, detail=detail)
        return response.json()

    async def aclose(self) -> None:
        await self._client.aclose()


def _get_language(context: ContextTypes.DEFAULT_TYPE, settings: Settings) -> str:
    return str(context.user_data.get("language", settings.default_response_language))


def _get_selected_language(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    language = context.user_data.get("language")
    if isinstance(language, str) and language in {"en", "zh-CN"}:
        return language
    return None


def _language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "简体中文", callback_data=f"{LANG_CALLBACK_PREFIX}zh-CN"
                ),
                InlineKeyboardButton(
                    "English", callback_data=f"{LANG_CALLBACK_PREFIX}en"
                ),
            ]
        ]
    )


def _build_language_selector_text() -> str:
    return (
        "请选择语言 / Please choose your language:\n"
        "- 简体中文\n"
        "- English"
    )


def _start_view_keyboard(language: str) -> InlineKeyboardMarkup:
    if language == "zh-CN":
        rows = [
            [
                InlineKeyboardButton(
                    "功能总览",
                    callback_data=f"{START_VIEW_CALLBACK_PREFIX}overview",
                ),
                InlineKeyboardButton(
                    "面试链接",
                    callback_data=f"{START_VIEW_CALLBACK_PREFIX}link",
                ),
                InlineKeyboardButton(
                    "合约扫描",
                    callback_data=f"{START_VIEW_CALLBACK_PREFIX}contract",
                ),
            ],
            [
                InlineKeyboardButton(
                    "聊天分析",
                    callback_data=f"{START_VIEW_CALLBACK_PREFIX}chat",
                ),
                InlineKeyboardButton(
                    "防骗要点",
                    callback_data=f"{START_VIEW_CALLBACK_PREFIX}guide",
                ),
                InlineKeyboardButton(
                    "关于",
                    callback_data=f"{START_VIEW_CALLBACK_PREFIX}about",
                ),
            ],
        ]
    else:
        rows = [
            [
                InlineKeyboardButton(
                    "Overview",
                    callback_data=f"{START_VIEW_CALLBACK_PREFIX}overview",
                ),
                InlineKeyboardButton(
                    "Interview Link",
                    callback_data=f"{START_VIEW_CALLBACK_PREFIX}link",
                ),
                InlineKeyboardButton(
                    "Contract Scan",
                    callback_data=f"{START_VIEW_CALLBACK_PREFIX}contract",
                ),
            ],
            [
                InlineKeyboardButton(
                    "Chat Analysis",
                    callback_data=f"{START_VIEW_CALLBACK_PREFIX}chat",
                ),
                InlineKeyboardButton(
                    "Anti-Scam Tips",
                    callback_data=f"{START_VIEW_CALLBACK_PREFIX}guide",
                ),
                InlineKeyboardButton(
                    "About",
                    callback_data=f"{START_VIEW_CALLBACK_PREFIX}about",
                ),
            ],
        ]
    return InlineKeyboardMarkup(rows)


def _build_start_overview(language: str) -> str:
    if language == "zh-CN":
        return (
            "KerryWeb3Guard 已就绪。\n"
            "为方便阅读，内容已拆分成模块，点击下方按钮查看详情。\n\n"
            "—— 快速入口 ——\n"
            "1) /checkin  每日签到 +5（每日自动+3）\n"
            "2) /link     面试链接安全扫描\n"
            "3) /chat     聊天记录安全分析\n"
            "4) /contract 链上合约地址扫描\n"
            "5) /learn_scam 反诈套路学习\n"
            "6) /invite   邀请奖励（双方各 +20）\n"
            "7) /quota    查看额度钱包\n"
            "8) /estimate 用户名查 ID 并估算新旧\n"
            "9) /lang     切换语言\n\n"
            "提示：首次使用建议先 /checkin，再按需选择功能。"
        )
    return (
        "KerryWeb3Guard is ready.\n"
        "Content is split into modules for readability. Tap buttons below.\n\n"
        "—— Quick Entry ——\n"
        "1) /checkin   Daily +5 bonus (daily auto +3)\n"
        "2) /link      Interview link safety scan\n"
        "3) /chat      Chat log safety analysis\n"
        "4) /contract  On-chain contract address scan\n"
        "5) /learn_scam Anti-scam pattern learning\n"
        "6) /invite    Referral reward (+20 for both)\n"
        "7) /quota     Check quota wallet\n"
        "8) /estimate  Resolve username + estimate account age\n"
        "9) /lang      Switch language\n\n"
        "Tip: New users can start with /checkin first."
    )


def _build_scam_pattern_keyboard(
    pattern_catalog: list[dict[str, Any]],
) -> InlineKeyboardMarkup | None:
    rows: list[list[InlineKeyboardButton]] = []
    for item in pattern_catalog[:6]:
        if not isinstance(item, dict):
            continue
        pattern_id = str(item.get("pattern_id", "")).strip()
        name = str(item.get("name", "")).strip()
        if not pattern_id or not name:
            continue
        rows.append(
            [
                InlineKeyboardButton(
                    name,
                    callback_data=f"{SCAM_CALLBACK_PREFIX}{pattern_id}",
                )
            ]
        )
    if not rows:
        return None
    return InlineKeyboardMarkup(rows)


def _build_help_message(language: str) -> str:
    if language == "zh-CN":
        return (
            "帮助中心（快速上手）\n\n"
            "/checkin\n"
            "- 每日签到，额外 +5 点。\n\n"
            "/link <网址>\n"
            "- 面试链接安全扫描分析（结论 + 依据）。\n"
            "  例：/link https://example.com\n\n"
            "/chat <聊天内容>\n"
            "- 识别诈骗话术，返回风险评分与建议。\n"
            "  例：/chat \"粘贴对应的TG聊天记录到这里\"\n\n"
            "/contract <chain> <contract_address>\n"
            "- 扫描链上合约风险（交易、持仓、LP等）。\n"
            "  例：/contract eth 0x...\n\n"
            "/learn_scam <问题>\n"
            "- 互动式学习常见防骗套路（先选套路，再由 AI 讲解）。\n"
            "  例：/learn_scam 对方面试前5分钟发链接还催我下载软件\n\n"
            "  例：/learn_scam 有哪些常见骗术？\n\n"
            "/invite\n"
            "- 获取邀请链接；每邀请成功1人，双方各 +20 点。\n\n"
            "/estimate @username\n"
            "- 通过 Telegram API 获取用户 ID，并按 ID 估算账号新旧。\n\n"
            "/quota\n"
            "- 查看额度账户（初始5点，每天自动+3，签到/邀请可加成）。\n\n"
            "/lang <en|zh-CN>\n"
            "- 切换语言（会影响帮助文案和AI回复语言）。"
        )

    return (
        "Help Center (quick start)\n\n"
        "/checkin\n"
        "- Daily check-in to get +5 bonus points.\n\n"
        "/link <url>\n"
        "- Interview link safety scan with conclusion + evidence.\n"
        "  Example: /link https://example.com\n\n"
        "/chat <message>\n"
        "- Analyze scam conversation risk and return evidence-based advice.\n"
        "  Example: /chat \"Paste the TG chat log here\"\n\n"
        "/contract <chain> <contract_address>\n"
        "- Scan on-chain contract risk (trading, holder, LP signals).\n"
        "  Example: /contract eth 0x...\n\n"
        "/learn_scam <question>\n"
        "- Interactive scam learning (select pattern, then AI explains).\n"
        "  Example: /learn_scam Recruiter pushed a last-minute download link.\n\n"
        "  Example: /learn_scam What are common scam patterns?\n\n"
        "/invite\n"
        "- Get your invite link. Each successful invite gives both sides +20 points.\n\n"
        "/estimate @username\n"
        "- Resolve user ID via Telegram API and estimate account age by ID.\n\n"
        "/quota\n"
        "- Show quota wallet (initial 5, daily +3, bonus via check-in/invite).\n\n"
        "/lang <en|zh-CN>\n"
        "- Switch language (affects help text and AI reply language)."
    )


def _build_processing_message(language: str) -> str:
    if language == "zh-CN":
        return (
            "已收到请求，正在分析中，请稍等（通常 5-20 秒）。\n"
            "结果返回前，请勿点击其他功能按钮或重复发送命令。\n"
            "上一条请求仍在处理中。请等待结果返回后，再继续点击其他功能"
        )
    return (
        "Request received. Analyzing now, please wait (usually 5-20s).\n"
        "Before the result returns, please do not tap other feature buttons "
        "or resend commands."
    )


def _is_user_processing(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return bool(context.user_data.get("processing_lock", False))


def _set_user_processing(context: ContextTypes.DEFAULT_TYPE, value: bool) -> None:
    context.user_data["processing_lock"] = value


def _build_busy_message(language: str) -> str:
    if language == "zh-CN":
        return "上一条请求仍在处理中。请等待结果返回后，再继续点击其他功能。"
    return (
        "A previous request is still processing. Please wait for the result "
        "before using other features."
    )


async def _check_overload_mode(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    action: str,
) -> bool:
    settings = context.application.bot_data.get("settings")
    if not isinstance(settings, Settings) or not settings.overload_mode_enabled:
        return False

    text = settings.overload_mode_message.strip() or (
        "当前请求较多，系统正在排队处理中，请稍后再试。"
    )
    _log_usage(update, context, action=action, status="overload")

    query = update.callback_query
    if query is not None:
        await _safe_answer_callback(query, text)
        return True

    if update.effective_message is not None:
        await update.effective_message.reply_text(text)
    return True


def _build_error_message(language: str, scan_name: str, detail: str) -> str:
    clean_detail = detail.strip()
    if not clean_detail:
        if language == "zh-CN":
            clean_detail = "服务暂时不可用，请稍后重试（可能正在重启）。"
        else:
            clean_detail = (
                "Service is temporarily unavailable. Please retry in a moment."
            )
    if language == "zh-CN":
        return f"{scan_name}失败：{clean_detail}"
    return f"{scan_name} failed: {clean_detail}"


def _get_quota_manager(context: ContextTypes.DEFAULT_TYPE) -> QuotaManager | None:
    manager = context.application.bot_data.get(QUOTA_MANAGER_KEY)
    if isinstance(manager, QuotaManager):
        return manager
    return None


def _build_quota_text(language: str, status: dict[str, int | str | bool]) -> str:
    balance = int(status["balance"])
    lifetime_used = int(status["lifetime_used"])
    initial_quota = int(status["initial_quota"])
    base_quota = int(status["base_quota"])
    checkin_bonus = int(status["checkin_bonus_quota"])
    invite_bonus = int(status["invite_bonus_quota"])
    checked_in_today = bool(status["checked_in_today"])
    invite_count = int(status["invite_count"])
    invite_code = str(status["invite_code"])

    if language == "zh-CN":
        checkin_text = "已签到" if checked_in_today else "未签到"
        return (
            "额度账户状态：\n"
            f"- 当前点数：{balance}\n"
            f"- 累计消耗：{lifetime_used}\n"
            f"- 初始点数：{initial_quota}\n"
            f"- 每日自动增加：+{base_quota}\n"
            f"- 今日签到：{checkin_text}\n"
            f"- 签到奖励：+{checkin_bonus}（命令：/checkin）\n"
            f"- 邀请奖励：+{invite_bonus}（命令：/invite）\n"
            f"- 已成功邀请：{invite_count}\n"
            f"- 你的邀请码：{invite_code}"
        )

    checkin_text = "Done" if checked_in_today else "Not yet"
    return (
        "Quota wallet status:\n"
        f"- Current points: {balance}\n"
        f"- Lifetime used: {lifetime_used}\n"
        f"- Initial points: {initial_quota}\n"
        f"- Daily auto top-up: +{base_quota}\n"
        f"- Check-in today: {checkin_text}\n"
        f"- Check-in reward: +{checkin_bonus} (/checkin)\n"
        f"- Invite reward: +{invite_bonus} (/invite)\n"
        f"- Successful invites: {invite_count}\n"
        f"- Your invite code: {invite_code}"
    )


def _build_quota_exhausted_text(language: str, required: int, balance: int) -> str:
    if language == "zh-CN":
        return (
            f"当前点数不足（当前 {balance}，本次需要 {required}）。\n"
            "可先使用 /checkin 领取奖励，或邀请好友获取更多点数。"
        )
    return (
        f"Insufficient points (current {balance}, required {required}).\n"
        "Use /checkin or invite friends for more points."
    )


def _build_quota_hint(language: str, status: dict[str, int | str | bool]) -> str:
    balance = int(status["balance"])
    if language == "zh-CN":
        return f"（当前点数：{balance}）"
    return f"(Current points: {balance})"


def _normalize_telegram_username(raw: str) -> str | None:
    text = raw.strip()
    if not text:
        return None
    if text.startswith("https://t.me/"):
        text = text.split("https://t.me/", 1)[1].strip("/")
    if text.startswith("@"):
        text = text[1:]
    if not re.fullmatch(r"[A-Za-z0-9_]{5,32}", text):
        return None
    return f"@{text}"


def _estimate_id_age_bucket(user_id: int, language: str) -> tuple[str, str]:
    # Heuristic only: Telegram does not expose official registration time.
    if user_id >= 7_000_000_000:
        if language == "zh-CN":
            return ("疑似较新账号", "低")
        return ("Likely newer account", "low")
    if user_id >= 5_000_000_000:
        if language == "zh-CN":
            return ("可能偏新账号", "低")
        return ("Possibly newer account", "low")
    if user_id >= 3_000_000_000:
        if language == "zh-CN":
            return ("账号年龄中等", "低")
        return ("Mid-age account", "low")
    if language == "zh-CN":
        return ("疑似较老账号", "低")
    return ("Likely older account", "low")


def _build_estimate_resolve_failed_text(language: str, username: str) -> str:
    if language == "zh-CN":
        return (
            "无法通过 Telegram API 解析该用户名对应的用户 ID。\n"
            f"目标用户名：{username}\n\n"
            "这通常是 Bot API 可见性限制（并非系统故障）。\n"
            "请确认用户名存在且公开，然后稍后重试。"
        )
    return (
        "Unable to resolve this username to a user ID via Telegram API.\n"
        f"Target username: {username}\n\n"
        "This is usually a Bot API visibility limit (not a system error).\n"
        "Please confirm the username is valid/public and try again later."
    )


def _build_estimate_result_text(language: str, username: str, user_id: int) -> str:
    bucket, confidence = _estimate_id_age_bucket(user_id, language)
    if language == "zh-CN":
        return (
            "账号年龄估算（基于用户 ID）\n"
            f"- 用户名：{username}\n"
            f"- 用户 ID：{user_id}\n"
            f"- 估算结果：{bucket}\n"
            f"- 置信度：{confidence}\n\n"
            "说明：Telegram 不提供官方注册时间，本结果仅供风控参考。"
        )
    return (
        "Account age estimate (ID-based)\n"
        f"- Username: {username}\n"
        f"- User ID: {user_id}\n"
        f"- Estimate: {bucket}\n"
        f"- Confidence: {confidence}\n\n"
        "Note: Telegram does not expose official registration time."
    )


async def _send_processing_feedback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    language: str,
) -> Message:
    return await update.effective_message.reply_text(_build_processing_message(language))


async def _safe_edit_status(
    status_message: Message,
    text: str,
    update: Update,
) -> None:
    try:
        await status_message.edit_text(text)
    except Exception:
        await update.effective_message.reply_text(text)


async def _safe_edit_callback_message(
    query: Any,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    try:
        await query.edit_message_text(text, reply_markup=reply_markup)
    except BadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


async def _safe_answer_callback(query: Any, text: str | None = None) -> bool:
    try:
        if text is None:
            await query.answer()
        else:
            await query.answer(text)
        return True
    except BadRequest as exc:
        error_text = str(exc).lower()
        if "query is too old" in error_text or "query id is invalid" in error_text:
            return False
        raise


def _fmt_scan_output(data: dict[str, Any], language: str) -> str:
    risk_score = data.get("risk_score", "N/A")
    if language == "zh-CN":
        summary_default = "暂无总结"
        advice_default = "暂无建议"
        reasons_title = "理由"
        summary_title = "总结"
        advice_title = "建议"
    else:
        summary_default = "No summary"
        advice_default = "No advice"
        reasons_title = "Reasons"
        summary_title = "Summary"
        advice_title = "Advice"

    summary = str(data.get("summary", summary_default))
    advice = str(data.get("advice", data.get("recommended_action", advice_default)))
    reasons = data.get("reasons", data.get("evidence_points", []))
    reasons_text = "\n".join(f"- {item}" for item in reasons[:5]) if reasons else "- N/A"

    return (
        f"Risk Score: {risk_score}\n"
        f"{summary_title}: {summary}\n\n"
        f"{reasons_title}:\n{reasons_text}\n\n"
        f"{advice_title}: {advice}"
    )


def _split_for_display(
    text: str,
    language: str,
    max_items: int = 4,
    max_chars_each: int = 110,
) -> list[str]:
    content = text.strip()
    if not content:
        return []

    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        lines = [content]

    separators = ["。", "！", "？", "；"] if language == "zh-CN" else [".", "!", "?", ";"]
    chunks: list[str] = []
    for line in lines:
        parts = [line]
        for sep in separators:
            next_parts: list[str] = []
            for part in parts:
                split_parts = [p.strip() for p in part.split(sep)]
                for item in split_parts:
                    if item:
                        next_parts.append(item)
            parts = next_parts
        chunks.extend(parts)

    if not chunks:
        chunks = [content]

    compact: list[str] = []
    for item in chunks:
        normalized = " ".join(item.split()) if language != "zh-CN" else item
        normalized = normalized.lstrip("-• ").strip()
        if not normalized:
            continue
        compact.append(_truncate_text(normalized, max_chars=max_chars_each))
        if len(compact) >= max_items:
            break
    return compact


def _pattern_display_name(data: dict[str, Any], pattern_id: str) -> str:
    catalog = data.get("pattern_catalog", [])
    if not isinstance(catalog, list):
        return pattern_id
    for item in catalog:
        if not isinstance(item, dict):
            continue
        if str(item.get("pattern_id", "")).strip() != pattern_id:
            continue
        name = str(item.get("name", "")).strip()
        if name:
            return name
    return pattern_id


def _fmt_scam_learn_output(data: dict[str, Any], language: str) -> str:
    topic = str(data.get("topic", "N/A"))
    intro = str(data.get("intro", "N/A"))
    selected_pattern_id = str(data.get("selected_pattern_id", "unknown"))
    explanation = str(data.get("explanation", "N/A"))
    checklist = data.get("interactive_checklist", [])
    questions = data.get("next_questions", [])
    pattern_name = _pattern_display_name(data, selected_pattern_id)

    if language == "zh-CN":
        pattern_title = "当前讲解"
        pattern_id_title = "套路ID"
        explanation_title = "核心解读"
        checklist_title = "快速核验清单"
        questions_title = "继续追问（可直接复制）"
    else:
        pattern_title = "Current Pattern"
        pattern_id_title = "Pattern ID"
        explanation_title = "Core Explanation"
        checklist_title = "Quick Checklist"
        questions_title = "Ask Next (copy-ready)"

    explanation_points = _split_for_display(explanation, language, max_items=4)
    explanation_lines = (
        "\n".join(f"- {line}" for line in explanation_points)
        if explanation_points
        else "- N/A"
    )
    checklist_lines = (
        "\n".join(f"- {line}" for line in checklist[:4]) if checklist else "- N/A"
    )
    question_lines = (
        "\n".join(f"- {line}" for line in questions[:3]) if questions else "- N/A"
    )

    return (
        f"{topic}\n"
        f"{intro}\n\n"
        f"{pattern_title}: {pattern_name}\n"
        f"{pattern_id_title}: {selected_pattern_id}\n\n"
        f"{explanation_title}:\n{explanation_lines}\n\n"
        f"{checklist_title}:\n{checklist_lines}\n\n"
        f"{questions_title}:\n{question_lines}"
    )


def _fmt_scam_catalog_output(data: dict[str, Any], language: str) -> str:
    if language == "zh-CN":
        title = "互动式防骗套路学习"
        hint = "你可以点击下方套路卡片，也可以直接输入框发文字对话或追问套路细节。"
    else:
        title = "Interactive Anti-Scam Pattern Learning"
        hint = "You can tap a pattern card below or ask follow-up questions in plain text."
    return f"{title}\n\n{hint}"


def _build_scam_mode_enabled_text(language: str) -> str:
    if language == "zh-CN":
        return (
            "你已进入防骗套路学习对话模式。\n"
            "发送任意其他命令（如 /chat /link /contract）会自动退出学习模式。"
        )
    return (
        "Scam-learning conversation mode is enabled.\n"
        "Using any other command (e.g. /chat /link /contract) will auto-exit this learn mode."
    )


def _deactivate_scam_mode(context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not context.user_data.get(SCAM_MODE_KEY):
        return False
    context.user_data[SCAM_MODE_KEY] = False
    context.user_data.pop(SCAM_PATTERN_KEY, None)
    return True


def _auto_exit_scam_mode_on_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    command_name: str,
) -> None:
    if _deactivate_scam_mode(context):
        _log_usage(
            update,
            context,
            action="learn_scam_auto_exit",
            status="ok",
            details={"by_command": command_name},
        )


def _local_scam_playbook_catalog(language: str) -> list[dict[str, str]]:
    if language == "zh-CN":
        return [dict(item) for item in SCAM_PLAYBOOK_CATALOG_ZH]
    return [dict(item) for item in SCAM_PLAYBOOK_CATALOG_EN]


def _format_guide_item(item: dict[str, Any]) -> str:
    text = str(item.get("text", "")).strip()
    if not text:
        return ""
    return f"- {text}"


def _localize_source(language: str, source: str) -> str:
    if language != "zh-CN":
        return source

    source_map = {
        "KerryWeb3Guard community anti-scam rules (creator experience).": (
            "KerryWeb3Guard 社区反诈规则（创作者实战经验）。"
        ),
        "General hiring best practices (industry standard).": (
            "通用正规招聘最佳实践（行业标准）。"
        ),
    }
    return source_map.get(source, source)


def _chunk_text(text: str, max_chars: int = 3500) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > max_chars:
            if current:
                chunks.append(current.rstrip())
                current = ""
            # Fallback for exceptionally long single line.
            while len(line) > max_chars:
                chunks.append(line[:max_chars])
                line = line[max_chars:]
        current += line

    if current:
        chunks.append(current.rstrip())
    return chunks


def _build_start_message(language: str, guide: dict[str, Any] | None = None) -> str:
    is_zh = language == "zh-CN"

    if is_zh:
        header = (
            "学会赚钱前，先学会不被骗。\n"
            "TG 套路多，Kerry 来帮你。\n\n"
            "KerryWeb3Guard 已就绪。\n"
            "你的 Web3 反诈助手。"
        )
        action_hint = (
            "推荐顺序：\n"
            "1./checkin（先签到领 +5）\n"
            "2./link（面试链接检测）\n"
            "3./chat（聊天骗子识别）\n"
            "4./contract（链上合约检测）\n"
            "5./learn_scam（反诈套路学习）\n"
            "6./invite（邀请奖励）\n"
            "7./quota（查看额度）\n"
            "8./estimate（用户名查 ID + 估算）\n"
            "9./lang（切换语言）"
        )
        value_block = (
            "功能：\n"
            "1) 面试链接安全扫描\n"
            "   识别面试链接是否可疑（域名、下载来源、链接格式）。\n"
            "   用法：/link <网址>\n"
            "   例：/link https://meet.google.com.verify-login.example/\n\n"
            "2) 聊天记录安全分析（判断对方是否是骗子）\n"
            "   分析对话中的诈骗话术并给出风险建议。\n"
            "   用法：/chat <聊天内容>\n"
            "   例：/chat \"粘贴对应的TG聊天记录到这里\"\n\n"
            "3) 链上合约地址安全扫描\n"
            "   评估交易、持仓、LP、源码公开等风险信号。\n"
            "   用法：/contract <chain> <合约地址>\n"
            "   例：/contract eth 0x...\n\n"
            "4) 互动式防骗套路学习\n"
            "   先选套路，再由 AI 讲解，并可继续追问细节。\n"
            "   用法A（防骗套路目录）：/learn_scam\n"
            "   例：/learn_scam\n"
            "   用法B（直接提问）：/learn_scam <问题>\n"
            "   例：/learn_scam 对方面试前5分钟发链接并催我安装软件怎么办？\n\n"
            "   例：/learn_scam 有哪些常见骗术？\n\n"
            "   提示：发送其他命令会自动退出该学习模式\n\n"

        )
        scam_title = "诈骗常见套路："
        legit_title = "正规公司常见做法："
        empty_guide = "（暂未加载到指南，可先使用 /chat 发送可疑话术）"
        creator = (
            "项目创作者：Telegram @kerryzheng\n"
            "如你有新的反诈套路数据或骗子聊天记录，欢迎联系 @kerryzheng 提供线索。"
        )
    else:
        header = (
            "Before learning to make money, learn how not to get scammed.\n"
            "TG is full of traps. Kerry has your back.\n\n"
            "KerryWeb3Guard is ready.\n"
            "Your Web3 anti-scam assistant."
        )
        action_hint = (
            "Recommended order:\n"
            "1. /checkin (claim +5 first)\n"
            "2. /link (interview link scan)\n"
            "3. /chat (chat scam analysis)\n"
            "4. /contract (contract risk scan)\n"
            "5. /learn_scam (anti-scam learning)\n"
            "6. /invite (referral rewards)\n"
            "7. /quota (check wallet)\n"
            "8. /estimate (username -> ID + estimate)\n"
            "9. /lang (switch language)"
        )
        value_block = (
            "Features:\n"
            "1) Interview link safety scan\n"
            "   Detect suspicious interview links (domain, download source, URL format).\n"
            "   Usage: /link <url>\n"
            "   Example: /link https://meet.google.com.verify-login.example/\n\n"
            "2) Chat log safety analysis (is this person likely a scammer?)\n"
            "   Analyze scam patterns in messages and return actionable advice.\n"
            "   Usage: /chat <message>\n"
            "   Example: /chat \"Paste the TG chat log here\"\n\n"
            "3) On-chain contract address risk scan\n"
            "   Evaluate trading, holder, LP, and source-code exposure signals.\n"
            "   Usage: /contract <chain> <address>\n"
            "   Example: /contract eth 0x...\n\n"
            "4) Interactive Anti-Scam Pattern Learning\n"
            "   Select a pattern first, then get AI explanation and follow-up Q&A.\n"
            "   Mode A (select first): /learn_scam\n"
            "   Mode B (ask directly): /learn_scam <question>\n"
            "   Example: /learn_scam I got a last-minute interview link.\n\n"
            "   Example: /learn_scam What are common scam patterns?\n\n"
            "   Note: using other commands will auto-exit this learning mode.\n\n"
            "Output: Risk Score + Summary + Reasons + Advice"
        )
        scam_title = "Common scam patterns:"
        legit_title = "What legit companies usually do:"
        empty_guide = "(Guide is temporarily unavailable. Try /chat first.)"
        creator = (
            "Project creator: Telegram @kerryzheng\n"
            "If you have new scam-pattern data or scam chat logs, contact "
            "@kerryzheng to share leads."
        )

    scam_lines: list[str] = []
    legit_lines: list[str] = []
    if guide:
        for item in guide.get("scam_knowledge", []):
            if isinstance(item, dict):
                item = {
                    **item,
                    "source": _localize_source(language, str(item.get("source", ""))),
                }
                line = _format_guide_item(item)
                if line:
                    scam_lines.append(line)
        for item in guide.get("legit_company_practices", []):
            if isinstance(item, dict):
                item = {
                    **item,
                    "source": _localize_source(language, str(item.get("source", ""))),
                }
                line = _format_guide_item(item)
                if line:
                    legit_lines.append(line)

    guide_text = empty_guide
    if scam_lines or legit_lines:
        scam_text = "\n".join(scam_lines) if scam_lines else "- N/A"
        legit_text = "\n".join(legit_lines) if legit_lines else "- N/A"
        guide_text = f"{scam_title}\n{scam_text}\n\n{legit_title}\n{legit_text}"

    return (
        f"{header}\n"
        f"{action_hint}\n\n"
        f"{value_block}\n\n"
        f"{guide_text}\n\n"
        f"{creator}"
    )


async def _fetch_start_guide(
    context: ContextTypes.DEFAULT_TYPE,
    language: str,
) -> dict[str, Any] | None:
    client = context.application.bot_data["backend_client"]
    try:
        result = await client.get("/api/v1/meta/start-guide", params={"language": language})
        if isinstance(result, dict):
            return result
    except Exception:
        return None
    return None


def _build_start_section_text(
    language: str,
    section: str,
    guide: dict[str, Any] | None = None,
) -> str:
    if section == "overview":
        return _build_start_overview(language)
    if section == "link":
        if language == "zh-CN":
            return (
                "面试链接安全扫描\n\n"
                "用途：识别面试链接风险（域名、下载来源、链接格式）。\n"
                "用法：/link <网址>\n"
                "示例：/link https://meet.google.com.verify-login.example/"
            )
        return (
            "Interview link safety scan\n\n"
            "Purpose: detect interview-link risks (domain, download source, URL format).\n"
            "Usage: /link <url>\n"
            "Example: /link https://meet.google.com.verify-login.example/"
        )
    if section == "contract":
        if language == "zh-CN":
            return (
                "链上合约地址安全扫描\n\n"
                "用途：评估交易、持仓、LP、源码公开等风险信号。\n"
                "用法：/contract <chain> <合约地址>\n"
                "示例：/contract eth 0x..."
            )
        return (
            "On-chain contract address risk scan\n\n"
            "Purpose: evaluate trading, holder, LP, and source-code exposure signals.\n"
            "Usage: /contract <chain> <address>\n"
            "Example: /contract eth 0x..."
        )
    if section == "chat":
        if language == "zh-CN":
            return (
                "聊天记录安全分析（判断对方是否是骗子）\n\n"
                "用途：分析诈骗话术并给出建议。\n"
                "用法：/chat <聊天内容>\n"
                "示例：/chat \"粘贴对应的TG聊天记录到这里\""
            )
        return (
            "Chat log safety analysis\n\n"
            "Purpose: analyze scam patterns in messages and return advice.\n"
            "Usage: /chat <message>\n"
            "Example: /chat \"Paste the TG chat log here\""
        )
    if section == "guide":
        if not guide:
            return (
                "（暂未加载到指南）"
                if language == "zh-CN"
                else "(Guide is temporarily unavailable)"
            )
        scam_lines = [
            _format_guide_item(
                {
                    **item,
                    "source": _localize_source(language, str(item.get("source", ""))),
                }
            )
            for item in guide.get("scam_knowledge", [])
            if isinstance(item, dict)
        ]
        legit_lines = [
            _format_guide_item(
                {
                    **item,
                    "source": _localize_source(language, str(item.get("source", ""))),
                }
            )
            for item in guide.get("legit_company_practices", [])
            if isinstance(item, dict)
        ]
        scam_lines = [item for item in scam_lines if item]
        legit_lines = [item for item in legit_lines if item]
        if language == "zh-CN":
            title_a = "诈骗常见套路："
            title_b = "正规公司常见做法："
        else:
            title_a = "Common scam patterns:"
            title_b = "What legit companies usually do:"
        return (
            f"{title_a}\n{'\n'.join(scam_lines) if scam_lines else '- N/A'}\n\n"
            f"{title_b}\n{'\n'.join(legit_lines) if legit_lines else '- N/A'}"
        )
    if section == "about":
        if language == "zh-CN":
            return (
                "关于 KerryWeb3Guard\n\n"
                "创建者：Telegram @kerryzheng\n\n"
                "这是一个为 Web3 用户打造的反诈助手。\n"
                "在你点击链接、下载软件、或者转账之前，先帮你看一眼。\n\n"
                "很多 Web3 用户其实每天都在面对这些情况：\n\n"
                "1️⃣ 突然来的“工作机会”\n"
                "对方说自己是某某项目 HR，邀请你面试。\n"
                "聊得很顺利，最后发来一个会议链接：\n"
                "“需要提前下载这个客户端。”\n"
                "你不知道——这是正常流程，还是钓鱼软件。\n\n"
                "2️⃣ Telegram 私信合作\n"
                "对方说：我们项目想合作 / 投资 / 上交易所。\n"
                "话术很专业，看起来像真的团队。\n"
                "但你心里总有一个问题：\n"
                "这个人到底是真的项目方，还是骗子？\n\n"
                "3️⃣ 看到一个新 Token\n"
                "社群里有人说这个币会涨 100 倍。\n"
                "你打开 Dex 想买，却发现：\n"
                "- 合约看不懂\n"
                "- LP 不知道锁没锁\n"
                "- 持仓结构也不会分析\n"
                "你只能靠感觉下注。\n\n"
                "Web3 的问题从来不是机会太少，\n"
                "而是骗局太多。\n\n"
                "KerryWeb3Guard 能帮你做三件事：\n\n"
                "🔍 面试链接检测\n"
                "把面试链接发给 Bot，它会分析：\n"
                "- 是否可能是钓鱼网站\n"
                "- 是否诱导下载恶意软件\n"
                "- 是否存在明显诈骗模式\n\n"
                "💬 聊天诈骗识别\n"
                "把 Telegram / Discord 的聊天记录发给 Bot，\n"
                "AI 会分析其中的社工话术和诈骗信号。\n\n"
                "🪙 合约风险分析\n"
                "输入 Token 合约地址，Bot 会分析：\n"
                "- 持仓结构\n"
                "- LP 锁定情况\n"
                "- 合约风险信号\n\n"
                "目标只有一个：\n"
                "在你点击、下载、或者转账之前，\n"
                "多一层判断。"
            )
        return (
            "About KerryWeb3Guard\n\n"
            "Creator: Telegram @kerryzheng\n\n"
            "KerryWeb3Guard is an anti-scam assistant built for Web3 users, "
            "especially:\n"
            "- Web3 job seekers and interview candidates\n"
            "- On-chain traders and newcomers\n"
            "- Community operators and security-conscious users\n\n"
            "User pain points:\n"
            "- Last-minute interview links and forced-download pressure are hard "
            "to verify quickly\n"
            "- Frequent DMs for jobs/collabs make scam scripts difficult to detect\n"
            "- On-chain contract data is complex and difficult for newcomers to "
            "judge in time\n\n"
            "Core goals:\n"
            "1) Detect interview-link risks (phishing/download traps)\n"
            "2) Detect scam patterns in chats (social engineering/urgency)\n"
            "3) Detect on-chain contract risk signals (trading/holder/LP/source)\n\n"
            "Positioning: one extra anti-scam decision layer before you click, "
            "download, or transfer funds."
        )
    return _build_start_overview(language)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    selected_language = _get_selected_language(context)
    language = selected_language or "zh-CN"
    if await _check_overload_mode(update, context, "start"):
        return
    if _check_free_command_cooldown(update, context, "start"):
        await update.effective_message.reply_text(
            "操作太快，请 1 秒后再试。" if language == "zh-CN" else "Too fast. Please retry in 1 second."
        )
        return
    _auto_exit_scam_mode_on_command(update, context, "start")
    user = update.effective_user
    quota_manager = _get_quota_manager(context)
    referral_code = _extract_referral_code(context)
    _log_usage(
        update,
        context,
        action="start",
        status="ok",
        details={"language_selected": selected_language is not None},
    )
    if referral_code and quota_manager is not None and user is not None:
        bind_status = quota_manager.bind_inviter(user.id, referral_code)
        _log_usage(
            update,
            context,
            action="invite_bind",
            status=bind_status,
            details={"code": _truncate_text(referral_code, max_chars=24)},
        )
        if bind_status == "bound":
            lang_for_text = selected_language or "zh-CN"
            text = (
                "邀请关系已绑定，完成首次检测后你和邀请人都将获得奖励点数。"
                if lang_for_text == "zh-CN"
                else "Invite link bound. Complete your first scan to unlock reward points for both sides."
            )
            await update.effective_message.reply_text(text)
    if selected_language is None:
        await update.effective_message.reply_text(
            _build_language_selector_text(),
            reply_markup=_language_keyboard(),
        )
        return

    await _send_start_overview(update, context, selected_language)


async def _send_start_content(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    language: str,
) -> None:
    guide = await _fetch_start_guide(context=context, language=language)

    message = _build_start_message(language=language, guide=guide)
    for chunk in _chunk_text(message):
        await update.effective_message.reply_text(chunk)


async def _send_start_overview(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    language: str,
) -> None:
    await update.effective_message.reply_text(
        _build_start_overview(language),
        reply_markup=_start_view_keyboard(language),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    language = _get_language(context, settings)
    if await _check_overload_mode(update, context, "help"):
        return
    if _check_free_command_cooldown(update, context, "help"):
        await update.effective_message.reply_text(
            "操作太快，请 1 秒后再试。" if language == "zh-CN" else "Too fast. Please retry in 1 second."
        )
        return
    _auto_exit_scam_mode_on_command(update, context, "help")
    _log_usage(update, context, action="help", status="ok", details={"language": language})
    await update.effective_message.reply_text(_build_help_message(language))


async def quota_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    language = _get_language(context, settings)
    if await _check_overload_mode(update, context, "quota"):
        return
    if _check_free_command_cooldown(update, context, "quota"):
        await update.effective_message.reply_text(
            "操作太快，请 1 秒后再试。" if language == "zh-CN" else "Too fast. Please retry in 1 second."
        )
        return
    _auto_exit_scam_mode_on_command(update, context, "quota")
    user = update.effective_user
    manager = _get_quota_manager(context)
    if user is None or manager is None:
        await update.effective_message.reply_text(
            "服务暂不可用，请稍后重试。" if language == "zh-CN" else "Service unavailable."
        )
        return
    status = manager.get_status(user.id)
    _log_usage(
        update,
        context,
        action="quota",
        status="ok",
        details={"balance": status["balance"]},
    )
    await update.effective_message.reply_text(_build_quota_text(language, status))


async def checkin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    language = _get_language(context, settings)
    if await _check_overload_mode(update, context, "checkin"):
        return
    if _check_free_command_cooldown(update, context, "checkin"):
        await update.effective_message.reply_text(
            "操作太快，请 1 秒后再试。" if language == "zh-CN" else "Too fast. Please retry in 1 second."
        )
        return
    _auto_exit_scam_mode_on_command(update, context, "checkin")
    user = update.effective_user
    manager = _get_quota_manager(context)
    if user is None or manager is None:
        await update.effective_message.reply_text(
            "服务暂不可用，请稍后重试。" if language == "zh-CN" else "Service unavailable."
        )
        return
    awarded, status = manager.check_in(user.id)
    _log_usage(
        update,
        context,
        action="checkin",
        status="ok" if awarded else "already_checked_in",
        details={"balance": status["balance"]},
    )
    bonus_value = int(status["checkin_bonus_quota"])
    if language == "zh-CN":
        headline = (
            f"签到成功，已增加 +{bonus_value} 次额度。"
            if awarded
            else "今天已经签到过了。"
        )
    else:
        headline = (
            f"Check-in successful. +{bonus_value} quota added."
            if awarded
            else "You already checked in today."
        )
    await update.effective_message.reply_text(f"{headline}\n\n{_build_quota_text(language, status)}")


async def invite_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    language = _get_language(context, settings)
    if await _check_overload_mode(update, context, "invite"):
        return
    if _check_free_command_cooldown(update, context, "invite"):
        await update.effective_message.reply_text(
            "操作太快，请 1 秒后再试。" if language == "zh-CN" else "Too fast. Please retry in 1 second."
        )
        return
    _auto_exit_scam_mode_on_command(update, context, "invite")
    user = update.effective_user
    manager = _get_quota_manager(context)
    if user is None or manager is None:
        await update.effective_message.reply_text(
            "服务暂不可用，请稍后重试。" if language == "zh-CN" else "Service unavailable."
        )
        return

    code = manager.get_invite_code(user.id)
    username = context.bot.username
    if not username:
        bot_info = await context.bot.get_me()
        username = bot_info.username or ""
    invite_link = (
        f"https://t.me/{username}?start=ref_{code}"
        if username
        else f"邀请码：ref_{code}"
    )
    status = manager.get_status(user.id)
    _log_usage(
        update,
        context,
        action="invite",
        status="ok",
        details={"invite_code": code, "invite_count": status["invite_count"]},
    )
    bonus = int(status["invite_bonus_quota"])
    if language == "zh-CN":
        text = (
            "邀请好友奖励已开启。\n"
            f"- 每邀请成功 1 人，你和对方各得 +{bonus} 点\n"
            "- 成功标准：对方通过你的链接进入并完成首次有效检测\n\n"
            f"你的邀请链接：\n{invite_link}\n\n"
            f"已成功邀请：{status['invite_count']} 人"
        )
    else:
        text = (
            "Invite rewards are enabled.\n"
            f"- For each successful invite, both sides get +{bonus} points\n"
            "- Success rule: invited user joins via your link and finishes first scan\n\n"
            f"Your invite link:\n{invite_link}\n\n"
            f"Successful invites: {status['invite_count']}"
        )
    await update.effective_message.reply_text(text)


async def estimate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    language = _get_language(context, settings)
    if await _check_overload_mode(update, context, "estimate"):
        return
    if _check_free_command_cooldown(update, context, "estimate"):
        await update.effective_message.reply_text(
            "操作太快，请 1 秒后再试。"
            if language == "zh-CN"
            else "Too fast. Please retry in 1 second."
        )
        return
    _auto_exit_scam_mode_on_command(update, context, "estimate")
    if not context.args:
        _log_usage(update, context, action="estimate", status="missing_arg")
        usage = (
            "用法：/estimate @username\n"
            "示例：/estimate @example_user"
            if language == "zh-CN"
            else "Usage: /estimate @username\n"
            "Example: /estimate @example_user"
        )
        await update.effective_message.reply_text(usage)
        return

    username = _normalize_telegram_username(context.args[0])
    if not username:
        _log_usage(update, context, action="estimate", status="invalid_username")
        text = (
            "用户名格式无效。请使用 @username（5-32 位，字母/数字/下划线）。"
            if language == "zh-CN"
            else "Invalid username. Use @username (5-32 chars, letters/digits/_)."
        )
        await update.effective_message.reply_text(text)
        return

    try:
        chat = await context.bot.get_chat(username)
        user_id = getattr(chat, "id", None)
        if not isinstance(user_id, int):
            raise ValueError("resolved chat has no integer id")
    except (TelegramError, ValueError) as exc:
        _log_usage(
            update,
            context,
            action="estimate",
            status="resolve_failed",
            details={
                "username": username,
                "error": _truncate_text(str(exc), max_chars=120),
            },
        )
        await update.effective_message.reply_text(
            _build_estimate_resolve_failed_text(language, username)
        )
        return

    _log_usage(
        update,
        context,
        action="estimate",
        status="ok",
        details={"username": username, "target_user_id": user_id},
    )
    await update.effective_message.reply_text(
        _build_estimate_result_text(language, username, user_id)
    )


def _extract_referral_code(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    if not context.args:
        return None
    raw = context.args[0].strip()
    if not raw:
        return None
    if raw.startswith("ref_"):
        code = raw[4:]
        return code.strip() or None
    return None


async def _maybe_apply_invite_reward(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    language: str,
) -> str:
    user = update.effective_user
    manager = _get_quota_manager(context)
    if user is None or manager is None:
        return ""
    reward = manager.apply_invite_reward_on_first_success(user.id)
    if not bool(reward.get("applied")):
        return ""
    reward_value = int(reward.get("reward", 0))
    inviter_id = int(reward.get("inviter_id", 0))
    _log_usage(
        update,
        context,
        action="invite_reward",
        status="applied",
        details={"reward": reward_value, "inviter_id": inviter_id},
    )
    if language == "zh-CN":
        return (
            f"\n\n🎉 邀请奖励已发放：你已获得 +{reward_value} 点（邀请人也已获得同等奖励）。"
        )
    return (
        f"\n\n🎉 Invite reward granted: you received +{reward_value} points "
        "(your inviter also received the same bonus)."
    )


async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current_language = _get_selected_language(context) or "zh-CN"
    if await _check_overload_mode(update, context, "lang"):
        return
    if _check_free_command_cooldown(update, context, "lang"):
        await update.effective_message.reply_text(
            "操作太快，请 1 秒后再试。"
            if current_language == "zh-CN"
            else "Too fast. Please retry in 1 second."
        )
        return
    _auto_exit_scam_mode_on_command(update, context, "lang")
    if not context.args:
        _log_usage(update, context, action="lang", status="missing_arg")
        await update.effective_message.reply_text(
            _build_language_selector_text(),
            reply_markup=_language_keyboard(),
        )
        return
    lang = context.args[0].strip()
    if lang not in {"en", "zh-CN"}:
        _log_usage(
            update,
            context,
            action="lang",
            status="invalid_arg",
            details={"input": _truncate_text(lang, max_chars=16)},
        )
        await update.effective_message.reply_text(
            "Language must be en or zh-CN. 语言参数必须是 en 或 zh-CN。"
        )
        return
    context.user_data["language"] = lang
    _log_usage(update, context, action="lang", status="ok", details={"language": lang})
    if lang == "zh-CN":
        await update.effective_message.reply_text("语言已切换为中文。")
    else:
        await update.effective_message.reply_text("Language switched to English.")


async def on_language_selected(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    if not query.data.startswith(LANG_CALLBACK_PREFIX):
        return

    if await _check_overload_mode(update, context, "lang_callback"):
        return
    current_language = _get_selected_language(context) or "zh-CN"
    if _check_free_command_cooldown(update, context, "lang_callback"):
        await _safe_answer_callback(
            query,
            "操作太快，请 1 秒后再试。"
            if current_language == "zh-CN"
            else "Too fast. Please retry in 1 second.",
        )
        return

    lang = query.data[len(LANG_CALLBACK_PREFIX) :]
    if lang not in {"en", "zh-CN"}:
        _log_usage(
            update,
            context,
            action="lang_callback",
            status="invalid_arg",
            details={"input": _truncate_text(lang, max_chars=16)},
        )
        await _safe_answer_callback(query, "Unsupported language.")
        return

    context.user_data["language"] = lang
    _log_usage(
        update,
        context,
        action="lang_callback",
        status="ok",
        details={"language": lang},
    )
    if lang == "zh-CN":
        await _safe_answer_callback(query, "已切换中文")
        await _safe_edit_callback_message(
            query,
            "已切换为中文，下面是你的使用指南。",
        )
    else:
        await _safe_answer_callback(query, "Language updated")
        await _safe_edit_callback_message(
            query,
            "Language switched to English. Here is your guide.",
        )

    await _send_start_overview(update, context, lang)


async def on_start_view_selected(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    if not query.data.startswith(START_VIEW_CALLBACK_PREFIX):
        return

    if await _check_overload_mode(update, context, "start_view"):
        return
    section = query.data[len(START_VIEW_CALLBACK_PREFIX) :].strip()
    settings = context.application.bot_data["settings"]
    language = _get_language(context, settings)
    if _check_free_command_cooldown(update, context, "start_view"):
        await _safe_answer_callback(
            query,
            "操作太快，请 1 秒后再试。"
            if language == "zh-CN"
            else "Too fast. Please retry in 1 second.",
        )
        return
    if _is_user_processing(context):
        await _safe_answer_callback(query, _build_busy_message(language))
        return
    supported_sections = {"overview", "link", "contract", "chat", "guide", "about"}
    if section not in supported_sections:
        _log_usage(
            update,
            context,
            action="start_view",
            status="invalid_arg",
            details={"section": _truncate_text(section, max_chars=24)},
        )
        await _safe_answer_callback(query, "Unsupported section.")
        return

    _log_usage(
        update,
        context,
        action="start_view",
        status="ok",
        details={"section": section, "language": language},
    )
    await _safe_answer_callback(query)

    guide = await _fetch_start_guide(context=context, language=language)
    section_message = _build_start_section_text(language, section, guide)
    await _safe_edit_callback_message(
        query,
        section_message,
        reply_markup=_start_view_keyboard(language),
    )


async def contract_scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    language = _get_language(context, settings)
    if await _check_overload_mode(update, context, "contract_scan"):
        return
    _auto_exit_scam_mode_on_command(update, context, "contract")
    cost = max(1, int(settings.cost_contract_scan))
    user = update.effective_user
    quota_manager = _get_quota_manager(context)
    if len(context.args) < 2:
        _log_usage(update, context, action="contract_scan", status="missing_arg")
        usage = (
            "用法：/contract <chain> <contract_address>（输入链名和合约地址分析链上风险）\n"
            "示例：/contract eth 0x..."
            if language == "zh-CN"
            else "Usage: /contract <chain> <contract_address> "
            "(analyze on-chain contract risk)\n"
            "Example: /contract eth 0x..."
        )
        await update.effective_message.reply_text(usage)
        return

    client = context.application.bot_data["backend_client"]
    chain = context.args[0].strip().lower()
    contract_address = context.args[1].strip()
    payload = {
        "chain": chain,
        "contract_address": contract_address,
        "response_language": language,
    }
    if quota_manager is not None and user is not None:
        quota_status = quota_manager.get_status(user.id)
        if int(quota_status["balance"]) < cost:
            _log_usage(
                update,
                context,
                action="contract_scan",
                status="quota_exhausted",
                details={"required_cost": cost, "balance": quota_status["balance"]},
            )
            await update.effective_message.reply_text(
                f"{_build_quota_exhausted_text(language, cost, int(quota_status['balance']))}\n\n"
                f"{_build_quota_text(language, quota_status)}"
            )
            return
    if _is_user_processing(context):
        _log_usage(update, context, action="contract_scan", status="busy")
        await update.effective_message.reply_text(_build_busy_message(language))
        return
    _set_user_processing(context, True)
    try:
        started_at = time.perf_counter()
        _log_usage(
            update,
            context,
            action="contract_scan",
            status="received",
            details={"chain": chain, "contract_address": _truncate_text(contract_address, 20)},
        )
        status_message = await _send_processing_feedback(update, context, language)
        try:
            data = await client.post("/api/v1/scan/contract", payload)
        except BackendAPIError as exc:
            _log_usage(
                update,
                context,
                action="contract_scan",
                status="backend_error",
                started_at=started_at,
                details={"error": _truncate_text(exc.detail)},
            )
            await _safe_edit_status(
                status_message,
                _build_error_message(language, "Contract scan", exc.detail),
                update,
            )
            return
        except Exception as exc:
            _log_usage(
                update,
                context,
                action="contract_scan",
                status="error",
                started_at=started_at,
                details={"error": _truncate_text(str(exc))},
            )
            await _safe_edit_status(
                status_message,
                _build_error_message(language, "Contract scan", str(exc)),
                update,
            )
            return
        _log_usage(
            update,
            context,
            action="contract_scan",
            status="ok",
            started_at=started_at,
            details={"risk_score": data.get("risk_score")},
        )
        output_text = _fmt_scan_output(data, language)
        if quota_manager is not None and user is not None:
            quota_status = quota_manager.consume(user.id, amount=cost)
            reward_note = await _maybe_apply_invite_reward(update, context, language)
            if reward_note:
                quota_status = quota_manager.get_status(user.id)
            output_text = (
                f"{output_text}\n\n{_build_quota_hint(language, quota_status)}{reward_note}"
            )
        await _safe_edit_status(status_message, output_text, update)
        _log_usage(
            update,
            context,
            action="contract_scan",
            status="response_sent",
            details={"output": _log_text(context, output_text, default_max_chars=240)},
        )
    finally:
        _set_user_processing(context, False)


async def link_scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    language = _get_language(context, settings)
    if await _check_overload_mode(update, context, "link_scan"):
        return
    _auto_exit_scam_mode_on_command(update, context, "link")
    cost = max(1, int(settings.cost_link_scan))
    user = update.effective_user
    quota_manager = _get_quota_manager(context)
    if not context.args:
        _log_usage(update, context, action="link_scan", status="missing_arg")
        usage = (
            "用法：/link <url>（粘贴面试链接分析是否可疑）\n"
            "示例：/link https://example.com/meeting"
            if language == "zh-CN"
            else "Usage: /link <url> (paste interview link for risk check)\n"
            "Example: /link https://example.com/meeting"
        )
        await update.effective_message.reply_text(usage)
        return

    client = context.application.bot_data["backend_client"]
    url = " ".join(context.args).strip()
    payload = {
        "url": url,
        "response_language": language,
    }
    if quota_manager is not None and user is not None:
        quota_status = quota_manager.get_status(user.id)
        if int(quota_status["balance"]) < cost:
            _log_usage(
                update,
                context,
                action="link_scan",
                status="quota_exhausted",
                details={"required_cost": cost, "balance": quota_status["balance"]},
            )
            await update.effective_message.reply_text(
                f"{_build_quota_exhausted_text(language, cost, int(quota_status['balance']))}\n\n"
                f"{_build_quota_text(language, quota_status)}"
            )
            return
    if _is_user_processing(context):
        _log_usage(update, context, action="link_scan", status="busy")
        await update.effective_message.reply_text(_build_busy_message(language))
        return
    _set_user_processing(context, True)
    try:
        started_at = time.perf_counter()
        _log_usage(
            update,
            context,
            action="link_scan",
            status="received",
            details={"url": _log_text(context, url)},
        )
        status_message = await _send_processing_feedback(update, context, language)
        try:
            data = await client.post("/api/v1/scan/link", payload)
        except BackendAPIError as exc:
            detail = exc.detail
            if exc.status_code == 422:
                detail = (
                    "链接不被允许：仅支持公网 http/https 链接，且禁止 localhost、内网IP和本机地址。"
                    if language == "zh-CN"
                    else "URL not allowed: only public http/https targets are accepted; localhost and private/internal IPs are blocked."
                )
            _log_usage(
                update,
                context,
                action="link_scan",
                status="backend_error",
                started_at=started_at,
                details={"error": _truncate_text(exc.detail)},
            )
            await _safe_edit_status(
                status_message,
                _build_error_message(language, "Link scan", detail),
                update,
            )
            return
        except Exception as exc:
            _log_usage(
                update,
                context,
                action="link_scan",
                status="error",
                started_at=started_at,
                details={"error": _truncate_text(str(exc))},
            )
            await _safe_edit_status(
                status_message,
                _build_error_message(language, "Link scan", str(exc)),
                update,
            )
            return
        _log_usage(
            update,
            context,
            action="link_scan",
            status="ok",
            started_at=started_at,
            details={"risk_score": data.get("risk_score")},
        )
        output_text = _fmt_scan_output(data, language)
        if quota_manager is not None and user is not None:
            quota_status = quota_manager.consume(user.id, amount=cost)
            reward_note = await _maybe_apply_invite_reward(update, context, language)
            if reward_note:
                quota_status = quota_manager.get_status(user.id)
            output_text = (
                f"{output_text}\n\n{_build_quota_hint(language, quota_status)}{reward_note}"
            )
        await _safe_edit_status(status_message, output_text, update)
        _log_usage(
            update,
            context,
            action="link_scan",
            status="response_sent",
            details={"output": _log_text(context, output_text, default_max_chars=240)},
        )
    finally:
        _set_user_processing(context, False)


async def chat_scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    language = _get_language(context, settings)
    if await _check_overload_mode(update, context, "chat_scan"):
        return
    _auto_exit_scam_mode_on_command(update, context, "chat")
    cost = max(1, int(settings.cost_chat_scan))
    user = update.effective_user
    quota_manager = _get_quota_manager(context)
    if not context.args:
        _log_usage(update, context, action="chat_scan", status="missing_arg")
        usage = (
            "用法：/chat <text>（粘贴聊天记录或大致聊天内容总结分析对方是否诈骗）\n"
            "示例：/chat 对方让我下载不认识的会议软件并开屏幕共享，随后卡点发面试链接催我下载软件"
            if language == "zh-CN"
            else "Usage: /chat <text> "
            "(paste chat log to assess scam risk)\n"
            "Example: /chat Recruiter asked me to install unknown meeting software."
        )
        await update.effective_message.reply_text(usage)
        return

    client = context.application.bot_data["backend_client"]
    chat_text = " ".join(context.args).strip()
    payload = {
        "chat_text": chat_text,
        "response_language": language,
    }
    if quota_manager is not None and user is not None:
        quota_status = quota_manager.get_status(user.id)
        if int(quota_status["balance"]) < cost:
            _log_usage(
                update,
                context,
                action="chat_scan",
                status="quota_exhausted",
                details={"required_cost": cost, "balance": quota_status["balance"]},
            )
            await update.effective_message.reply_text(
                f"{_build_quota_exhausted_text(language, cost, int(quota_status['balance']))}\n\n"
                f"{_build_quota_text(language, quota_status)}"
            )
            return
    if _is_user_processing(context):
        _log_usage(update, context, action="chat_scan", status="busy")
        await update.effective_message.reply_text(_build_busy_message(language))
        return
    _set_user_processing(context, True)
    try:
        started_at = time.perf_counter()
        _log_usage(
            update,
            context,
            action="chat_scan",
            status="received",
            details={"chat_text": _log_text(context, chat_text)},
        )
        status_message = await _send_processing_feedback(update, context, language)
        try:
            data = await client.post("/api/v1/scan/chat", payload)
        except BackendAPIError as exc:
            if exc.status_code == 422:
                _log_usage(
                    update,
                    context,
                    action="chat_scan",
                    status="validation_error",
                    started_at=started_at,
                )
                short_text = (
                    "聊天内容太短，请至少输入 2 个字符。例如：/chat 你好，我收到一个可疑面试链接"
                    if language == "zh-CN"
                    else "Message is too short. Please enter at least 2 characters. "
                    "Example: /chat I got a suspicious interview link."
                )
                await _safe_edit_status(status_message, short_text, update)
                return
            _log_usage(
                update,
                context,
                action="chat_scan",
                status="backend_error",
                started_at=started_at,
                details={"error": _truncate_text(exc.detail)},
            )
            await _safe_edit_status(
                status_message,
                _build_error_message(language, "Chat scan", exc.detail),
                update,
            )
            return
        except Exception as exc:
            _log_usage(
                update,
                context,
                action="chat_scan",
                status="error",
                started_at=started_at,
                details={"error": _truncate_text(str(exc))},
            )
            await _safe_edit_status(
                status_message,
                _build_error_message(language, "Chat scan", str(exc)),
                update,
            )
            return
        _log_usage(
            update,
            context,
            action="chat_scan",
            status="ok",
            started_at=started_at,
            details={"risk_score": data.get("risk_score")},
        )
        output_text = _fmt_scan_output(data, language)
        if quota_manager is not None and user is not None:
            quota_status = quota_manager.consume(user.id, amount=cost)
            reward_note = await _maybe_apply_invite_reward(update, context, language)
            if reward_note:
                quota_status = quota_manager.get_status(user.id)
            output_text = (
                f"{output_text}\n\n{_build_quota_hint(language, quota_status)}{reward_note}"
            )
        await _safe_edit_status(status_message, output_text, update)
        _log_usage(
            update,
            context,
            action="chat_scan",
            status="response_sent",
            details={"output": _log_text(context, output_text, default_max_chars=240)},
        )
    finally:
        _set_user_processing(context, False)


async def learn_scam(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    language = _get_language(context, settings)
    if await _check_overload_mode(update, context, "learn_scam"):
        return
    user_question = " ".join(context.args).strip() if context.args else ""
    await _run_learn_scam(
        update=update,
        context=context,
        language=language,
        user_question=user_question,
        pattern_id=None,
        announce_mode=True,
        source="command",
    )


async def _run_learn_scam(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    language: str,
    user_question: str,
    pattern_id: str | None,
    announce_mode: bool,
    source: str,
) -> None:
    show_catalog_only = source == "command" and not user_question.strip() and not pattern_id
    settings = context.application.bot_data["settings"]
    cost = max(1, int(settings.cost_learn_scam))
    user = update.effective_user
    quota_manager = _get_quota_manager(context)
    if _is_user_processing(context):
        _log_usage(update, context, action="learn_scam", status="busy")
        query = update.callback_query
        if query is not None:
            await _safe_answer_callback(query, _build_busy_message(language))
        else:
            await update.effective_message.reply_text(_build_busy_message(language))
        return

    if quota_manager is not None and user is not None:
        quota_status = quota_manager.get_status(user.id)
        if int(quota_status["balance"]) < cost:
            _log_usage(
                update,
                context,
                action="learn_scam",
                status="quota_exhausted",
                details={"required_cost": cost, "balance": quota_status["balance"]},
            )
            await update.effective_message.reply_text(
                f"{_build_quota_exhausted_text(language, cost, int(quota_status['balance']))}\n\n"
                f"{_build_quota_text(language, quota_status)}"
            )
            return

    if show_catalog_only:
        started_at = time.perf_counter()
        _log_usage(
            update,
            context,
            action="learn_scam",
            status="received",
            details={"source": "catalog_only"},
        )
        catalog = _local_scam_playbook_catalog(language)

        context.user_data[SCAM_MODE_KEY] = True
        context.user_data.pop(SCAM_PATTERN_KEY, None)
        output_text = _fmt_scam_catalog_output({"pattern_catalog": catalog}, language)
        if quota_manager is not None and user is not None:
            quota_status = quota_manager.consume(user.id, amount=cost)
            reward_note = await _maybe_apply_invite_reward(update, context, language)
            if reward_note:
                quota_status = quota_manager.get_status(user.id)
            output_text = (
                f"{output_text}\n\n{_build_quota_hint(language, quota_status)}{reward_note}"
            )
        keyboard = _build_scam_pattern_keyboard(catalog)
        await update.effective_message.reply_text(output_text, reply_markup=keyboard)
        _log_usage(
            update,
            context,
            action="learn_scam",
            status="response_sent",
            started_at=started_at,
            details={"source": "catalog_only", "catalog_size": len(catalog)},
        )
        if announce_mode:
            await update.effective_message.reply_text(_build_scam_mode_enabled_text(language))
        return

    client = context.application.bot_data["backend_client"]
    payload = {
        "user_question": user_question,
        "pattern_id": pattern_id or "",
        "response_language": language,
    }

    _set_user_processing(context, True)
    try:
        started_at = time.perf_counter()
        _log_usage(
            update,
            context,
            action="learn_scam",
            status="received",
            details={
                "source": source,
                "pattern_id": pattern_id or "",
                "question": _log_text(context, user_question),
            },
        )
        status_message = await _send_processing_feedback(update, context, language)
        try:
            data = await client.post("/api/v1/learn/scam-patterns", payload)
        except BackendAPIError as exc:
            _log_usage(
                update,
                context,
                action="learn_scam",
                status="backend_error",
                started_at=started_at,
                details={"source": source, "error": _truncate_text(exc.detail)},
            )
            await _safe_edit_status(
                status_message,
                _build_error_message(language, "Scam learning", exc.detail),
                update,
            )
            return
        except Exception as exc:
            _log_usage(
                update,
                context,
                action="learn_scam",
                status="error",
                started_at=started_at,
                details={"source": source, "error": _truncate_text(str(exc))},
            )
            await _safe_edit_status(
                status_message,
                _build_error_message(language, "Scam learning", str(exc)),
                update,
            )
            return

        context.user_data[SCAM_MODE_KEY] = True
        context.user_data[SCAM_PATTERN_KEY] = data.get(
            "selected_pattern_id", pattern_id or ""
        )
        _log_usage(
            update,
            context,
            action="learn_scam",
            status="ok",
            started_at=started_at,
            details={
                "source": source,
                "selected_pattern_id": data.get("selected_pattern_id", ""),
            },
        )
        keyboard = _build_scam_pattern_keyboard(data.get("pattern_catalog", []))
        output_text = _fmt_scam_learn_output(data, language)
        if quota_manager is not None and user is not None:
            quota_status = quota_manager.consume(user.id, amount=cost)
            reward_note = await _maybe_apply_invite_reward(update, context, language)
            if reward_note:
                quota_status = quota_manager.get_status(user.id)
            output_text = (
                f"{output_text}\n\n{_build_quota_hint(language, quota_status)}{reward_note}"
            )
        try:
            await status_message.edit_text(output_text, reply_markup=keyboard)
        except Exception:
            await update.effective_message.reply_text(output_text, reply_markup=keyboard)
        _log_usage(
            update,
            context,
            action="learn_scam",
            status="response_sent",
            details={
                "source": source,
                "output": _log_text(context, output_text, default_max_chars=240),
            },
        )
        if announce_mode:
            await update.effective_message.reply_text(
                _build_scam_mode_enabled_text(language)
            )
    finally:
        _set_user_processing(context, False)


async def on_scam_pattern_selected(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    if not query.data.startswith(SCAM_CALLBACK_PREFIX):
        return

    if await _check_overload_mode(update, context, "learn_scam_button"):
        return
    settings = context.application.bot_data["settings"]
    language = _get_language(context, settings)
    if _is_user_processing(context):
        await _safe_answer_callback(query, _build_busy_message(language))
        return
    pattern_id = query.data[len(SCAM_CALLBACK_PREFIX) :].strip()
    if not pattern_id:
        await _safe_answer_callback(query, "Invalid pattern.")
        return
    await _safe_answer_callback(
        query, "Processing..." if language != "zh-CN" else "正在讲解..."
    )
    await _run_learn_scam(
        update=update,
        context=context,
        language=language,
        user_question="",
        pattern_id=pattern_id,
        announce_mode=False,
        source="button",
    )


async def on_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _check_overload_mode(update, context, "text_message"):
        return
    if not context.user_data.get(SCAM_MODE_KEY):
        return
    settings = context.application.bot_data["settings"]
    language = _get_language(context, settings)
    message = (update.effective_message.text or "").strip()
    if not message:
        return
    _log_usage(
        update,
        context,
        action="learn_scam_followup",
        status="received",
        details={"message": _log_text(context, message)},
    )

    stop_words = {"退出学习", "退出", "结束学习", "stop", "exit", "quit"}
    if message.lower() in stop_words or message in stop_words:
        _deactivate_scam_mode(context)
        _log_usage(update, context, action="learn_scam_stop_text", status="ok")
        text = (
            "已退出防骗套路学习对话模式。你可以随时再次输入 /learn_scam。"
            if language == "zh-CN"
            else "Scam-learning mode stopped. You can start again via /learn_scam."
        )
        await update.effective_message.reply_text(text)
        return

    selected_pattern_id = context.user_data.get(SCAM_PATTERN_KEY)
    pattern_id = str(selected_pattern_id) if isinstance(selected_pattern_id, str) else None
    await _run_learn_scam(
        update=update,
        context=context,
        language=language,
        user_question=message,
        pattern_id=pattern_id,
        announce_mode=False,
        source="follow_up",
    )


async def on_application_error(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    error = context.error
    logger = context.application.bot_data.get(USAGE_LOGGER_KEY)
    if not isinstance(logger, logging.Logger):
        logger = logging.getLogger("kerryweb3guard.usage")

    error_text = str(error) if error is not None else "Unknown error"
    # Network polling hiccups are common; keep logs concise for these.
    if "RemoteProtocolError" in error_text or isinstance(error, NetworkError):
        logger.warning(
            json.dumps(
                {
                    "event": "bot_error",
                    "type": "network",
                    "message": _truncate_text(error_text, max_chars=240),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return

    logger.exception(
        json.dumps(
            {
                "event": "bot_error",
                "type": "unhandled",
                "message": _truncate_text(error_text, max_chars=240),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )


async def on_startup(application: Application) -> None:
    default_commands = [
        BotCommand("start", "Start guide"),
        BotCommand("help", "Show help"),
        BotCommand("checkin", "Daily check-in for +5"),
        BotCommand("link", "Interview link safety scan"),
        BotCommand("chat", "Analyze suspicious chat"),
        BotCommand("contract", "Scan contract risk"),
        BotCommand("learn_scam", "Interactive Anti-Scam Pattern Learning"),
        BotCommand("invite", "Invite friends (+20 both)"),
        BotCommand("estimate", "Estimate account age by username"),
        BotCommand("quota", "Show quota wallet"),
        BotCommand("lang", "Switch language"),
    ]
    zh_commands = [
        BotCommand("start", "开始使用"),
        BotCommand("help", "查看帮助"),
        BotCommand("checkin", "每日签到+5额度"),
        BotCommand("link", "面试链接安全扫描分析"),
        BotCommand("chat", "诈骗话术识别"),
        BotCommand("contract", "合约风险扫描"),
        BotCommand("learn_scam", "互动式防骗套路学习"),
        BotCommand("invite", "邀请奖励（双方+20）"),
        BotCommand("estimate", "通过用户名估算账号新旧"),
        BotCommand("quota", "查看今日额度"),
        BotCommand("lang", "切换语言"),
    ]

    await application.bot.set_my_commands(default_commands)
    # Telegram expects ISO 639-1 language code; use "zh" for Chinese.
    try:
        await application.bot.set_my_commands(zh_commands, language_code="zh")
    except Exception:
        # Keep bot startup resilient even if localized command registration fails.
        pass


async def on_shutdown(application: Application) -> None:
    client = application.bot_data.get("backend_client")
    if isinstance(client, BackendClient):
        await client.aclose()


def main() -> None:
    settings = Settings()
    usage_logger = _setup_usage_logger(settings)
    quota_manager = _setup_quota_manager(settings)
    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(on_startup)
        .post_shutdown(on_shutdown)
        .build()
    )
    app.bot_data["settings"] = settings
    app.bot_data["backend_client"] = BackendClient(
        base_url=settings.api_base_url,
        timeout_seconds=settings.backend_http_timeout_seconds,
        max_connections=settings.backend_max_connections,
        max_keepalive_connections=settings.backend_max_keepalive_connections,
        keepalive_expiry_seconds=settings.backend_keepalive_expiry_seconds,
    )
    app.bot_data[USAGE_LOGGER_KEY] = usage_logger
    app.bot_data[QUOTA_MANAGER_KEY] = quota_manager
    usage_logger.info(
        json.dumps(
            {
                "event": "bot_startup",
                "api_base_url": settings.api_base_url,
                "backend_http_timeout_seconds": settings.backend_http_timeout_seconds,
                "backend_max_connections": settings.backend_max_connections,
                "backend_max_keepalive_connections": (
                    settings.backend_max_keepalive_connections
                ),
                "backend_keepalive_expiry_seconds": (
                    settings.backend_keepalive_expiry_seconds
                ),
                "free_command_cooldown_seconds": settings.free_command_cooldown_seconds,
                "usage_log_path": settings.usage_log_path,
                "quota_state_path": settings.quota_state_path,
                "initial_quota_points": settings.initial_quota_points,
                "daily_quota_base": settings.daily_quota_base,
                "checkin_bonus_quota": settings.checkin_bonus_quota,
                "invite_bonus_quota": settings.invite_bonus_quota,
                "cost_link_scan": settings.cost_link_scan,
                "cost_chat_scan": settings.cost_chat_scan,
                "cost_contract_scan": settings.cost_contract_scan,
                "cost_learn_scam": settings.cost_learn_scam,
                "log_full_io": settings.log_full_io,
                "log_full_io_max_chars": settings.log_full_io_max_chars,
                "overload_mode_enabled": settings.overload_mode_enabled,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("lang", set_language))
    app.add_handler(CommandHandler("quota", quota_command))
    app.add_handler(CommandHandler("checkin", checkin_command))
    app.add_handler(CommandHandler("invite", invite_command))
    app.add_handler(CommandHandler("estimate", estimate_command))
    app.add_handler(CallbackQueryHandler(on_language_selected, pattern=r"^lang:"))
    app.add_handler(CallbackQueryHandler(on_start_view_selected, pattern=r"^startview:"))
    app.add_handler(CallbackQueryHandler(on_scam_pattern_selected, pattern=r"^scam:"))
    app.add_handler(CommandHandler("learn_scam", learn_scam))
    app.add_handler(CommandHandler("contract", contract_scan))
    app.add_handler(CommandHandler("link", link_scan))
    app.add_handler(CommandHandler("chat", chat_scan))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text_message))
    app.add_error_handler(on_application_error)

    app.run_polling()


if __name__ == "__main__":
    main()
