export type SupportedLanguage = "en" | "zh-CN";

export type EducationItem = {
  title: string;
  meaning: string;
  points: string[];
};

type ContractEducationContent = {
  contractLogicItems: EducationItem[];
  commonScamItems: EducationItem[];
};

const zhCNContent: ContractEducationContent = {
  contractLogicItems: [
    {
      title: "交易行为（买方/卖方数量与交易量）",
      meaning: "用于判断是否存在单边拉盘、无法卖出或异常活跃等风险信号。",
      points: [
        "买方远高于卖方，可能存在诱多或 honeypot 风险",
        "卖方数量长期极低，需警惕无法正常退出",
        "总交易量突然放大，可能是短期操盘行为",
      ],
    },
    {
      title: "持仓结构（Top10 与其它地址占比）",
      meaning: "用于判断筹码是否过度集中，是否容易被少数钱包操控。",
      points: [
        "Top10 占比过高，可能存在控盘风险",
        "其它地址占比低，说明分散度不足",
        "持仓集中常伴随高波动和快速砸盘风险",
      ],
    },
    {
      title: "LP 情况（流动性与池子稳定性）",
      meaning: "用于判断交易深度和退出安全性，避免高滑点和抽池风险。",
      points: [
        "流动性过低时，价格容易被大单操控",
        "LP 提供方过少时，项目方控制力更强",
        "若 LP 锁定信息缺失，应提高风险权重",
      ],
    },
    {
      title: "源码公开状态（合约是否可审查）",
      meaning: "用于判断代码透明度，未公开源码的项目可解释性更差。",
      points: [
        "已验证源码更容易被社区与审计机构检查",
        "未公开源码难以确认后门、黑名单或税费逻辑",
        "源码未公开不等于必定诈骗，但需提高警惕",
      ],
    },
  ],
  commonScamItems: [
    {
      title: "Honeypot（可买难卖）",
      meaning: "诱导买入后限制卖出，制造“只能涨不能走”的错觉。",
      points: [
        "买方人数明显高于卖方",
        "卖出相关数据异常低",
        "源码未公开时风险进一步上升",
      ],
    },
    {
      title: "Rug Pull（抽池）",
      meaning: "项目方快速撤走流动性，导致价格断崖式下跌。",
      points: [
        "LP 流动性弱或提供方过少",
        "LP 锁定信息缺失或不明确",
        "持仓集中时更容易配合砸盘",
      ],
    },
    {
      title: "控盘拉砸（Pump & Dump）",
      meaning: "少数地址先拉盘吸引跟风，再集中抛售收割。",
      points: [
        "Top10 占比高",
        "短时间成交量异常放大",
        "价格波动和链上行为不匹配",
      ],
    },
    {
      title: "伪装项目（信息不透明）",
      meaning: "通过品牌包装降低警惕，但关键信息无法验证。",
      points: [
        "源码未公开或验证失败",
        "关键数据长期缺失",
        "多项指标同时显示不透明",
      ],
    },
  ],
};

const enContent: ContractEducationContent = {
  contractLogicItems: [
    {
      title: "Trading Behavior (buyers/sellers and volume)",
      meaning:
        "Used to detect one-sided momentum, sell restrictions, and unusual activity.",
      points: [
        "Buyers much higher than sellers can indicate lure-in patterns",
        "Very low seller count over time can signal exit limitations",
        "Sudden volume spikes may indicate short-term manipulation",
      ],
    },
    {
      title: "Holder Structure (Top10 vs others ratio)",
      meaning: "Used to evaluate concentration risk and potential wallet control.",
      points: [
        "High Top10 ratio can imply concentrated control",
        "Low others ratio means weak distribution",
        "Concentrated holding often increases dump risk",
      ],
    },
    {
      title: "LP Status (liquidity and pool stability)",
      meaning: "Used to estimate trade depth and exit safety under volatility.",
      points: [
        "Low liquidity increases price manipulation sensitivity",
        "Few LP providers can mean stronger project-side control",
        "Missing LP lock data should increase caution level",
      ],
    },
    {
      title: "Source Code Visibility (verified or not)",
      meaning:
        "Used to assess transparency. Unverified code is harder to trust.",
      points: [
        "Verified source is easier for community review",
        "Unverified source hides blacklist/tax/owner logic",
        "Unverified does not always mean scam, but risk is higher",
      ],
    },
  ],
  commonScamItems: [
    {
      title: "Honeypot (buyable, hard to sell)",
      meaning: "Lures users in with buy activity while restricting sell exits.",
      points: [
        "Buyer count is significantly higher than seller count",
        "Sell-side activity stays abnormally low",
        "Unverified source increases this risk",
      ],
    },
    {
      title: "Rug Pull",
      meaning: "Liquidity is withdrawn abruptly, causing sharp price collapse.",
      points: [
        "Weak LP liquidity or very few providers",
        "LP lock details missing or unclear",
        "High holder concentration amplifies dump impact",
      ],
    },
    {
      title: "Pump and Dump",
      meaning:
        "A small group pumps momentum first, then dumps into retail demand.",
      points: [
        "High Top10 concentration",
        "Abnormal short-term volume spike",
        "Price behavior inconsistent with healthy distribution",
      ],
    },
    {
      title: "Disguised Project (low transparency)",
      meaning:
        "Branding appears professional but key contract facts are unverifiable.",
      points: [
        "Source code is not verified",
        "Critical metrics remain unavailable",
        "Multiple transparency warnings appear together",
      ],
    },
  ],
};

export function getContractEducationContent(
  language: SupportedLanguage,
): ContractEducationContent {
  return language === "zh-CN" ? zhCNContent : enContent;
}
