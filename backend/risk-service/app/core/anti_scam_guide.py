from dataclasses import dataclass


START_GUIDE_ZH = [
    "面试临时发链接且不提前给，通常是制造紧迫感的高风险信号。",
    "不愿使用 Google Meet / Zoom / Lark 等主流会议工具，风险较高。",
    "不要轻易下载未知文件或安装不明软件。",
    "JD 与简历异常高匹配可能是定制化诱导，需要二次核验公司真实性。",
    "陌生私信给工作机会，先问来源渠道，再决定是否投递和提供信息。",
    "警惕伪装文件，例如 .docx.exe 这类实际可执行文件。",
    "索要身份证、银行卡、验证码等敏感信息可直接判定高风险。",
    "面试要求安装非主流工具（尤其未知来源）时应视为高风险。",
    "公司信息需独立核验；主流平台查无此项目时默认不信任。",
    "警惕“先跑代码/先做作业”：若项目里伪装 cache/log 文件并通过 curl/wget 拉取外部脚本，可能是木马投毒。",
]

START_GUIDE_EN = [
    "Interview links sent at the last minute are often urgency-based scam signals.",
    "Refusing mainstream tools like Google Meet/Zoom/Lark is high risk.",
    "Do not casually download unknown files or install untrusted software.",
    "A JD that matches your resume too perfectly can be bait and needs verification.",
    "If someone DMs you with a job, ask where they found you before sharing details.",
    "Watch for disguised files such as .docx.exe (actually executable files).",
    "Requests for ID, bank details, or verification codes are high-risk by default.",
    "If interview requires non-mainstream tools, treat it as suspicious.",
    "Always independently verify company legitimacy before proceeding.",
    "Be cautious with 'run this code first' tasks: cache/log-like files that use curl/wget to fetch external scripts may indicate malware delivery.",
]


@dataclass(frozen=True)
class ScamRule:
    rule_id: str
    title_zh: str
    title_en: str
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class GuideItem:
    text_zh: str
    text_en: str
    source: str


@dataclass(frozen=True)
class ScamPatternCard:
    pattern_id: str
    name_zh: str
    name_en: str
    scenario_zh: str
    scenario_en: str
    red_flags_zh: tuple[str, ...]
    red_flags_en: tuple[str, ...]
    safe_actions_zh: tuple[str, ...]
    safe_actions_en: tuple[str, ...]


SCAM_RULES: tuple[ScamRule, ...] = (
    ScamRule(
        "late_link",
        "临时发面试链接",
        "Late interview link",
        ("临时链接", "马上开会", "now", "urgent link", "last minute link"),
    ),
    ScamRule(
        "unknown_meeting_software",
        "要求安装非主流会议软件",
        "Unknown meeting software",
        ("下载奇怪会议软件", "安装奇怪软件", "unknown custom meeting app", "unknown app"),
    ),
    ScamRule(
        "suspicious_file",
        "可疑文件类型",
        "Suspicious file type",
        (".docx.exe", ".pdf.exe", ".zip.exe", ".scr", ".bat"),
    ),
    ScamRule(
        "sensitive_info_request",
        "索要敏感信息",
        "Sensitive information request",
        ("身份证", "银行卡", "验证码", "id card", "bank card", "otp", "cvv"),
    ),
    ScamRule(
        "resume_overmatch_bait",
        "JD 过度匹配诱导",
        "JD overmatch bait",
        ("简历很匹配", "99% match", "perfect match", "tailored for you"),
    ),
    ScamRule(
        "code_task_trojan_loader",
        "代码作业投毒（伪装 cache/log + 外链下载）",
        "Code-task trojan loader (fake cache/log + external download)",
        (
            "先跑代码",
            "先执行脚本",
            "cache.py",
            "log.py",
            "curl",
            "wget",
            "bash -c",
            "python -c",
            "run this script first",
            "debug package",
            "bootstrap script",
        ),
    ),
)

SCAM_KNOWLEDGE_BASE: tuple[GuideItem, ...] = (
    GuideItem(
        text_zh="面试卡点才发链接且不提前给，通常是制造紧迫感并诱导你下载软件。",
        text_en=(
            "If interview links are sent only at the last minute, it is often "
            "an urgency tactic to push unsafe downloads."
        ),
        source="KerryWeb3Guard community anti-scam rules (creator experience).",
    ),
    GuideItem(
        text_zh="要求下载非主流会议软件（非 Google Meet/Zoom/Lark）可视为高风险。",
        text_en=(
            "Requests to install non-mainstream meeting software are high-risk "
            "signals."
        ),
        source="KerryWeb3Guard community anti-scam rules (creator experience).",
    ),
    GuideItem(
        text_zh="陌生私信给工作机会时，先问来源渠道，再决定是否投递简历和信息。",
        text_en=(
            "When contacted via unsolicited job DMs, ask the source first before "
            "sharing your resume or personal information."
        ),
        source="KerryWeb3Guard community anti-scam rules (creator experience).",
    ),
    GuideItem(
        text_zh="警惕伪装文件（例如 .docx.exe），这类文件本质是可执行程序。",
        text_en=(
            "Watch for disguised files such as .docx.exe; these are executables, "
            "not documents."
        ),
        source="KerryWeb3Guard community anti-scam rules (creator experience).",
    ),
    GuideItem(
        text_zh="索要身份证、银行卡、验证码等敏感信息可直接判定为高风险。",
        text_en=(
            "Requests for ID cards, bank details, or OTP codes should be treated "
            "as high risk."
        ),
        source="KerryWeb3Guard community anti-scam rules (creator experience).",
    ),
    GuideItem(
        text_zh=(
            "警惕“代码作业/环境测试”套路：仓库中若出现伪装成 cache/log 的文件，"
            "并包含 curl/wget 拉外部脚本再执行，可能是木马投递链。"
        ),
        text_en=(
            "Watch for 'coding task/environment test' traps: cache/log-disguised "
            "files that use curl/wget to fetch and execute external scripts can "
            "be a malware delivery chain."
        ),
        source="KerryWeb3Guard community anti-scam rules (creator experience).",
    ),
)

LEGIT_COMPANY_PRACTICES: tuple[GuideItem, ...] = (
    GuideItem(
        text_zh="正规公司会提前确认面试时间，并在合理时间发送会议链接，不会突然给你发一个链接。",
        text_en=(
            "Legitimate companies usually confirm interview schedules in advance "
            "and share meeting links ahead of time."
        ),
        source="General hiring best practices (industry standard).",
    ),
    GuideItem(
        text_zh="正规流程通常使用主流工具，并给出可核验的公司域名邮箱或官网信息。",
        text_en=(
            "Legitimate processes usually use mainstream tools and verifiable "
            "company email/domain information."
        ),
        source="General hiring best practices (industry standard).",
    ),
    GuideItem(
        text_zh="正规招聘不会在早期要求身份证、银行卡或资产截图。",
        text_en=(
            "Legitimate hiring does not request ID cards, bank cards, or asset "
            "screenshots in early interview stages."
        ),
        source="General hiring best practices (industry standard).",
    ),
    GuideItem(
        text_zh="职位应可在官网、LinkedIn、或可信招聘渠道交叉验证。",
        text_en=(
            "Job postings should be cross-verified via official websites, LinkedIn, "
            "or trusted recruiting channels."
        ),
        source="General hiring best practices (industry standard).",
    ),
    GuideItem(
        text_zh=(
            "正规 Web3 公司或项目通常可在 CMC 等行情/项目平台查到；"
            "若查无信息且对方无法提供项目链接和公司官网，应保持警惕。"
        ),
        text_en=(
            "Legitimate Web3 companies/projects are usually discoverable on market/"
            "project platforms (e.g., CMC). If no listing is found and no official "
            "project link or company website is provided, treat it as high caution."
        ),
        source="General hiring best practices (industry standard).",
    ),
)


SCAM_PATTERN_PLAYBOOK: tuple[ScamPatternCard, ...] = (
    ScamPatternCard(
        pattern_id="last_minute_link_urgency",
        name_zh="卡点发链接 + 制造紧迫感",
        name_en="Last-minute link + urgency pressure",
        scenario_zh=(
            "对方在面试开始前几分钟才发链接，并催促你立刻下载/安装软件。"
        ),
        scenario_en=(
            "The recruiter sends a link minutes before interview and pressures "
            "you to install software immediately."
        ),
        red_flags_zh=(
            "不提前发会议链接，强调“现在就点”。",
            "使用未知域名或伪装成主流会议平台的链接。",
            "拒绝给你核验时间，持续催促。",
        ),
        red_flags_en=(
            "No advance meeting link; they insist you click now.",
            "Unknown domain or lookalike meeting URL.",
            "No time allowed for verification; constant urgency push.",
        ),
        safe_actions_zh=(
            "要求改用官方 Google Meet/Zoom/Lark 链接。",
            "延后面试并独立核验公司和岗位。",
            "任何下载都只走官网或应用商店。",
        ),
        safe_actions_en=(
            "Ask for an official Google Meet/Zoom/Lark link.",
            "Reschedule and independently verify company + job posting.",
            "Only download from official sites/app stores.",
        ),
    ),
    ScamPatternCard(
        pattern_id="non_mainstream_meeting_software",
        name_zh="要求安装非主流会议软件",
        name_en="Forced install of unknown meeting app",
        scenario_zh=(
            "对方要求你安装你从未见过的会议软件，且下载源不是官方渠道。"
        ),
        scenario_en=(
            "You are asked to install an unknown meeting app from a "
            "non-official source."
        ),
        red_flags_zh=(
            "不给官方站点下载地址。",
            "安装包后缀可疑（.exe/.scr/.bat）。",
            "要求开远程控制或屏幕录制权限。",
        ),
        red_flags_en=(
            "No official download page provided.",
            "Suspicious installer suffixes (.exe/.scr/.bat).",
            "Requests remote-control or broad screen permissions.",
        ),
        safe_actions_zh=(
            "拒绝安装未知软件，改用主流会议工具。",
            "必须下载时只用官网并核对签名发布者。",
            "不授予远程控制权限。",
        ),
        safe_actions_en=(
            "Decline unknown software; switch to mainstream tools.",
            "If download is unavoidable, use official source and verify signer.",
            "Never grant remote-control permissions.",
        ),
    ),
    ScamPatternCard(
        pattern_id="resume_overmatch_bait",
        name_zh="JD 99% 匹配诱导",
        name_en="JD 99% perfect-match bait",
        scenario_zh=(
            "岗位描述与你简历高度一致，强调“专门为你准备”，诱导你快速进入流程。"
        ),
        scenario_en=(
            "JD appears perfectly tailored to your resume and pushes you to move "
            "fast without verification."
        ),
        red_flags_zh=(
            "岗位信息在官网和可信平台无法交叉验证。",
            "HR 回避团队/业务细节问题。",
            "流程一开始就索要隐私或财务信息。",
        ),
        red_flags_en=(
            "Role cannot be cross-verified on official channels.",
            "Recruiter avoids basic team/business details.",
            "Sensitive or financial data requested too early.",
        ),
        safe_actions_zh=(
            "要求提供官网岗位链接和公司邮箱沟通。",
            "只通过可信渠道投递，不在私聊直接交敏感信息。",
            "对“过于完美机会”先做冷处理核验。",
        ),
        safe_actions_en=(
            "Ask for official posting URL and company-domain email follow-up.",
            "Use trusted channels; never share sensitive data in DMs.",
            "Slow down and verify before acting on a perfect offer.",
        ),
    ),
    ScamPatternCard(
        pattern_id="unsolicited_dm_job_offer",
        name_zh="陌生私信工作机会",
        name_en="Unsolicited DM job offer",
        scenario_zh=(
            "陌生账号直接私信高薪工作，要求先发简历或个人信息。"
        ),
        scenario_en=(
            "A stranger DM offers high-pay job and asks for resume/personal data "
            "immediately."
        ),
        red_flags_zh=(
            "无法说明在哪里看到你的资料。",
            "话术模板化、信息模糊。",
            "急于索要联系方式、身份证明或验证码。",
        ),
        red_flags_en=(
            "Cannot explain where they found your profile.",
            "Template-like scripts with vague details.",
            "Pushes for contacts, identity docs, or OTP quickly.",
        ),
        safe_actions_zh=(
            "先问来源渠道并要求可核验的职位信息。",
            "只提供最小必要信息，敏感资料一律不发。",
            "可疑账号直接拉黑并截图留证。",
        ),
        safe_actions_en=(
            "Ask source channel and verifiable job details first.",
            "Share minimum required info; never share sensitive docs.",
            "Block suspicious account and keep screenshots as evidence.",
        ),
    ),
    ScamPatternCard(
        pattern_id="code_task_trojan_loader",
        name_zh="代码作业投毒（伪装 cache/log + curl 拉取）",
        name_en="Code-task malware loader (fake cache/log + curl fetch)",
        scenario_zh=(
            "对方让你先跑一个“面试作业/环境检测”项目，仓库里混入看似正常的 "
            "cache/log 文件，实则会下载并执行外部恶意脚本。"
        ),
        scenario_en=(
            "You are asked to run an 'interview task/env check' repo where "
            "cache/log-like files silently download and execute external payloads."
        ),
        red_flags_zh=(
            "首次运行就要求执行未知 shell/python 脚本。",
            "代码里出现 curl/wget 拉远程地址后直接执行。",
            "文件命名伪装成 cache/log/debug，但行为与日志无关。",
        ),
        red_flags_en=(
            "First step requires executing unknown shell/python scripts.",
            "Code uses curl/wget to fetch remote content and execute it.",
            "Files named cache/log/debug perform non-logging network actions.",
        ),
        safe_actions_zh=(
            "不要在主力机器执行未知仓库，先隔离环境审计代码。",
            "重点审查启动脚本、依赖安装脚本和外联下载命令。",
            "发现外链下载并执行时，立即停止并要求对方说明来源与用途。",
        ),
        safe_actions_en=(
            "Never run unknown repos on your primary machine; audit in isolation.",
            "Review bootstrap/install scripts and all external download commands.",
            "Stop immediately if fetched content is executed; request provenance.",
        ),
    ),
)


def get_start_guide(language: str) -> list[str]:
    return START_GUIDE_ZH if language == "zh-CN" else START_GUIDE_EN


def get_start_sections(language: str) -> dict[str, list[dict[str, str]]]:
    if language == "zh-CN":
        scam_items = [
            {"text": item.text_zh, "source": item.source}
            for item in SCAM_KNOWLEDGE_BASE
        ]
        legit_items = [
            {"text": item.text_zh, "source": item.source}
            for item in LEGIT_COMPANY_PRACTICES
        ]
    else:
        scam_items = [
            {"text": item.text_en, "source": item.source}
            for item in SCAM_KNOWLEDGE_BASE
        ]
        legit_items = [
            {"text": item.text_en, "source": item.source}
            for item in LEGIT_COMPANY_PRACTICES
        ]

    return {
        "scam_knowledge": scam_items,
        "legit_company_practices": legit_items,
    }


def detect_scam_rules(chat_text: str, language: str) -> list[str]:
    content = chat_text.lower()
    hits: list[str] = []
    for rule in SCAM_RULES:
        if any(keyword.lower() in content for keyword in rule.keywords):
            title = rule.title_zh if language == "zh-CN" else rule.title_en
            hits.append(title)
    return hits


def get_scam_pattern_playbook(language: str) -> list[dict[str, str | list[str]]]:
    cards: list[dict[str, str | list[str]]] = []
    for card in SCAM_PATTERN_PLAYBOOK:
        if language == "zh-CN":
            cards.append(
                {
                    "pattern_id": card.pattern_id,
                    "name": card.name_zh,
                    "scenario": card.scenario_zh,
                    "red_flags": list(card.red_flags_zh),
                    "safe_actions": list(card.safe_actions_zh),
                }
            )
        else:
            cards.append(
                {
                    "pattern_id": card.pattern_id,
                    "name": card.name_en,
                    "scenario": card.scenario_en,
                    "red_flags": list(card.red_flags_en),
                    "safe_actions": list(card.safe_actions_en),
                }
            )
    return cards
