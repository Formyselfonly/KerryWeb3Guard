import i18n from "i18next";
import { initReactI18next } from "react-i18next";

const resources = {
  en: {
    translation: {
      appTitle: "KerryChainGuard",
      appSubtitle: "Web3 Safety Assistant",
      language: "Language",
      runAnalysis: "Run",
      loading: "Loading...",
      result: "Result",
      modules: {
        contract: "On-chain Contract Risk Scan",
        link: "Interview Link Safety Check",
        chat: "Scam Chat Analyzer",
        learn: "Web3 Learning Hub",
        blacklist: "Scam Blacklist Board",
      },
      fields: {
        chain: "Chain",
        chainHint: "Choose a chain from DexScreener supported list",
        contractAddress: "Contract Address",
        url: "URL",
        chatText: "Chat Text",
        topic: "Topic",
        userQuestion: "Question",
        reporterContact: "Your Contact",
        platform: "Platform",
        suspectedHandle: "Suspected Scammer Handle",
        description: "Description",
        evidenceLinks: "Evidence Links (one per line)",
      },
      actions: {
        submitReport: "Submit Report",
        loadList: "Load Blacklist",
      },
      sections: {
        dataView: "Raw Data Snapshot",
        tradingMetrics: "Trading Metrics",
        holderMetrics: "Holder Metrics",
        lpMetrics: "LP Metrics",
        sourceCodeMetrics: "Source Code Metrics",
        dataWarnings: "Data Warnings",
        aiConclusion: "AI Conclusion",
      },
    },
  },
  "zh-CN": {
    translation: {
      appTitle: "KerryChainGuard",
      appSubtitle: "Web3 安全助手",
      language: "语言",
      runAnalysis: "开始分析",
      loading: "加载中...",
      result: "结果",
      modules: {
        contract: "链上合约风险扫描",
        link: "面试链接安全检测",
        chat: "诈骗聊天分析",
        learn: "Web3 学习中心",
        blacklist: "骗子黑名单",
      },
      fields: {
        chain: "链名称",
        chainHint: "请从 DexScreener 支持的链列表中选择",
        contractAddress: "合约地址",
        url: "链接",
        chatText: "聊天内容",
        topic: "主题",
        userQuestion: "问题",
        reporterContact: "你的联系方式",
        platform: "平台",
        suspectedHandle: "可疑骗子账号",
        description: "描述",
        evidenceLinks: "证据链接（每行一个）",
      },
      actions: {
        submitReport: "提交举报",
        loadList: "加载黑名单",
      },
      sections: {
        dataView: "原始数据视图",
        tradingMetrics: "交易数据",
        holderMetrics: "持仓数据",
        lpMetrics: "LP 数据",
        sourceCodeMetrics: "源码公开状态",
        dataWarnings: "数据提示",
        aiConclusion: "AI 结论",
      },
    },
  },
};

i18n.use(initReactI18next).init({
  resources,
  lng: "en",
  fallbackLng: "en",
  interpolation: {
    escapeValue: false,
  },
});

export default i18n;
