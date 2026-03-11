import axios from "axios";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { getContractEducationContent } from "./content/contractEducation";
import "./App.css";

// Project Creator: Telegram @kerryzheng
type ModuleKey = "contract" | "link" | "chat" | "learn" | "blacklist";
type Language = "en" | "zh-CN";
type NumberOrNull = number | null;

type ContractMetrics = {
  trading: {
    buy_count_24h: number;
    sell_count_24h: number;
    buy_volume_usd_24h: NumberOrNull;
    sell_volume_usd_24h: NumberOrNull;
    total_volume_usd_24h: number;
  };
  holders: {
    top_10_ratio_percent: NumberOrNull;
    others_ratio_percent: NumberOrNull;
    note: string;
  };
  lp: {
    pair_count: number;
    liquidity_usd: number;
    lp_provider_count: NumberOrNull;
    lp_locked_ratio_percent: NumberOrNull;
  };
  source_code: {
    is_public: boolean | null;
    status: string;
    source_platform: string | null;
    check_url: string | null;
    note: string;
  };
};

type ContractScanResult = {
  module: "contract_risk_scan";
  risk_score: number;
  summary: string;
  reasons: string[];
  advice: string;
  metrics: ContractMetrics;
  data_warnings: string[];
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const toPercent = (value: number, total: number): number => {
  if (total <= 0) return 0;
  return Math.round((value / total) * 100);
};

const isContractScanResult = (value: unknown): value is ContractScanResult => {
  if (!value || typeof value !== "object") {
    return false;
  }
  const candidate = value as { module?: string; metrics?: unknown };
  return candidate.module === "contract_risk_scan" && Boolean(candidate.metrics);
};

function App() {
  const { t, i18n } = useTranslation();
  const [moduleKey, setModuleKey] = useState<ModuleKey>("contract");
  const [language, setLanguage] = useState<Language>("en");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<unknown>(null);
  const [blacklist, setBlacklist] = useState<unknown[]>([]);
  const [supportedChains, setSupportedChains] = useState<string[]>([
    "ethereum",
    "bsc",
    "solana",
    "base",
    "arbitrum",
  ]);

  const [chain, setChain] = useState("bsc");
  const [contractAddress, setContractAddress] = useState("");
  const [url, setUrl] = useState("");
  const [chatText, setChatText] = useState("");
  const [topic, setTopic] = useState("");
  const [userQuestion, setUserQuestion] = useState("");
  const [reporterContact, setReporterContact] = useState("");
  const [platform, setPlatform] = useState("Telegram");
  const [suspectedHandle, setSuspectedHandle] = useState("");
  const [description, setDescription] = useState("");
  const [evidenceLinks, setEvidenceLinks] = useState("");

  useEffect(() => {
    const saved = localStorage.getItem("kcg_language") as Language | null;
    if (saved) {
      setLanguage(saved);
      void i18n.changeLanguage(saved);
    }
  }, [i18n]);

  useEffect(() => {
    const loadChains = async () => {
      try {
        const response = await axios.get<string[]>(
          `${API_BASE_URL}/api/v1/meta/chains`,
        );
        if (Array.isArray(response.data) && response.data.length > 0) {
          setSupportedChains(response.data);
          if (!response.data.includes(chain)) {
            setChain(response.data[0]);
          }
        }
      } catch {
        // Keep frontend fallback options when backend metadata is unavailable.
      }
    };
    void loadChains();
  }, []);

  const onLanguageChange = async (value: Language) => {
    setLanguage(value);
    localStorage.setItem("kcg_language", value);
    await i18n.changeLanguage(value);
  };

  const request = axios.create({ baseURL: API_BASE_URL });
  const { contractLogicItems, commonScamItems } =
    getContractEducationContent(language);
  const renderMarkdown = (content: string) => (
    <div className="markdownContent">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setResult(null);
    try {
      if (moduleKey === "contract") {
        const response = await request.post("/api/v1/scan/contract", {
          chain,
          contract_address: contractAddress,
          response_language: language,
        });
        setResult(response.data);
      } else if (moduleKey === "link") {
        const response = await request.post("/api/v1/scan/link", {
          url,
          response_language: language,
        });
        setResult(response.data);
      } else if (moduleKey === "chat") {
        const response = await request.post("/api/v1/scan/chat", {
          chat_text: chatText,
          response_language: language,
        });
        setResult(response.data);
      } else if (moduleKey === "learn") {
        const response = await request.post("/api/v1/learn/web3", {
          topic,
          user_question: userQuestion,
          response_language: language,
        });
        setResult(response.data);
      } else {
        const response = await request.post("/api/v1/blacklist/report", {
          reporter_contact: reporterContact,
          platform,
          suspected_handle: suspectedHandle,
          description,
          evidence_links: evidenceLinks
            .split("\n")
            .map((item) => item.trim())
            .filter(Boolean),
          response_language: language,
        });
        setResult(response.data);
      }
    } catch (error) {
      setResult({
        error: "Request failed",
        detail: String(error),
      });
    } finally {
      setLoading(false);
    }
  };

  const loadBlacklist = async () => {
    setLoading(true);
    try {
      const response = await request.get("/api/v1/blacklist");
      setBlacklist(response.data);
    } catch (error) {
      setResult({ error: "Load blacklist failed", detail: String(error) });
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="container">
      <header className="header">
        <div>
          <h1>{t("appTitle")}</h1>
          <p>{t("appSubtitle")}</p>
        </div>
        <div className="langSwitcher">
          <label>{t("language")}</label>
          <select
            value={language}
            onChange={(event) => onLanguageChange(event.target.value as Language)}
          >
            <option value="en">English</option>
            <option value="zh-CN">中文</option>
          </select>
        </div>
      </header>

      <section className="moduleTabs">
        {(["contract", "link", "chat", "learn", "blacklist"] as ModuleKey[]).map(
          (key) => (
            <button
              className={moduleKey === key ? "active" : ""}
              key={key}
              onClick={() => setModuleKey(key)}
              type="button"
            >
              {t(`modules.${key}`)}
            </button>
          ),
        )}
      </section>

      <form className="panel" onSubmit={submit}>
        {moduleKey === "contract" && (
          <>
            <label>{t("fields.chain")}</label>
            <select value={chain} onChange={(event) => setChain(event.target.value)}>
              {supportedChains.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
            <small>{t("fields.chainHint")}</small>
            <label>{t("fields.contractAddress")}</label>
            <input
              required
              placeholder="0x..."
              value={contractAddress}
              onChange={(event) => setContractAddress(event.target.value)}
            />
          </>
        )}

        {moduleKey === "link" && (
          <>
            <label>{t("fields.url")}</label>
            <input required value={url} onChange={(event) => setUrl(event.target.value)} />
          </>
        )}

        {moduleKey === "chat" && (
          <>
            <label>{t("fields.chatText")}</label>
            <textarea
              required
              rows={6}
              value={chatText}
              onChange={(event) => setChatText(event.target.value)}
            />
          </>
        )}

        {moduleKey === "learn" && (
          <>
            <label>{t("fields.topic")}</label>
            <input value={topic} onChange={(event) => setTopic(event.target.value)} />
            <label>{t("fields.userQuestion")}</label>
            <textarea
              rows={5}
              value={userQuestion}
              onChange={(event) => setUserQuestion(event.target.value)}
            />
          </>
        )}

        {moduleKey === "blacklist" && (
          <>
            <label>{t("fields.reporterContact")}</label>
            <input
              required
              value={reporterContact}
              onChange={(event) => setReporterContact(event.target.value)}
            />
            <label>{t("fields.platform")}</label>
            <input value={platform} onChange={(event) => setPlatform(event.target.value)} />
            <label>{t("fields.suspectedHandle")}</label>
            <input
              required
              value={suspectedHandle}
              onChange={(event) => setSuspectedHandle(event.target.value)}
            />
            <label>{t("fields.description")}</label>
            <textarea
              required
              rows={5}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
            <label>{t("fields.evidenceLinks")}</label>
            <textarea
              rows={4}
              value={evidenceLinks}
              onChange={(event) => setEvidenceLinks(event.target.value)}
            />
          </>
        )}

        <div className="actions">
          <button type="submit" disabled={loading}>
            {loading ? t("loading") : moduleKey === "blacklist"
              ? t("actions.submitReport")
              : t("runAnalysis")}
          </button>
          {moduleKey === "blacklist" && (
            <button type="button" onClick={loadBlacklist}>
              {t("actions.loadList")}
            </button>
          )}
        </div>
      </form>

      {moduleKey === "contract" && (
        <section className="panel">
          <h3>
            {language === "zh-CN" ? "合约分析逻辑" : "Contract Analysis Logic"}
          </h3>
          <div className="educationGrid">
            {contractLogicItems.map((item) => (
              <article className="educationCard" key={item.title}>
                <h5>{item.title}</h5>
                <p>{item.meaning}</p>
                <ul>
                  {item.points.map((point) => (
                    <li key={point}>{point}</li>
                  ))}
                </ul>
              </article>
            ))}
          </div>

          <h3>{language === "zh-CN" ? "常见骗术介绍" : "Common Scam Playbook"}</h3>
          <div className="educationGrid">
            {commonScamItems.map((item) => (
              <article className="educationCard" key={item.title}>
                <h5>{item.title}</h5>
                <p>{item.meaning}</p>
                <ul>
                  {item.points.map((point) => (
                    <li key={point}>{point}</li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        </section>
      )}

      <section className="panel resultPanel">
        <h3>{t("result")}</h3>
        {moduleKey === "contract" && isContractScanResult(result) ? (
          <div className="contractResult">
            <h4>{t("sections.dataView")}</h4>
            <div className="metricsGrid">
              <article>
                <h5>{t("sections.tradingMetrics")}</h5>
                {(() => {
                  const buy = result.metrics.trading.buy_count_24h;
                  const sell = result.metrics.trading.sell_count_24h;
                  const total = buy + sell;
                  const buyPct = toPercent(buy, total);
                  const sellPct = 100 - buyPct;
                  return (
                    <div className="compareBlock">
                      <div className="compareHeader">
                        <span>Buy vs Sell</span>
                        <span>
                          {buyPct}% / {sellPct}%
                        </span>
                      </div>
                      <div className="compareBar">
                        <div
                          className="barBuy"
                          style={{ width: `${buyPct}%` }}
                          title={`Buyers: ${buy}`}
                        />
                        <div
                          className="barSell"
                          style={{ width: `${sellPct}%` }}
                          title={`Sellers: ${sell}`}
                        />
                      </div>
                      <div className="compareLegend">
                        <span className="legendBuy">Buy {buy}</span>
                        <span className="legendSell">Sell {sell}</span>
                      </div>
                    </div>
                  );
                })()}
                <div className="kvList">
                  <div className="kvItem">
                    <span>Buyers (24h)</span>
                    <strong>{result.metrics.trading.buy_count_24h}</strong>
                  </div>
                  <div className="kvItem">
                    <span>Sellers (24h)</span>
                    <strong>{result.metrics.trading.sell_count_24h}</strong>
                  </div>
                  {result.metrics.trading.buy_volume_usd_24h !== null && (
                    <div className="kvItem">
                      <span>Buy Volume (24h)</span>
                      <strong>{result.metrics.trading.buy_volume_usd_24h}</strong>
                    </div>
                  )}
                  {result.metrics.trading.sell_volume_usd_24h !== null && (
                    <div className="kvItem">
                      <span>Sell Volume (24h)</span>
                      <strong>{result.metrics.trading.sell_volume_usd_24h}</strong>
                    </div>
                  )}
                  <div className="kvItem">
                    <span>Total Volume (24h)</span>
                    <strong>{result.metrics.trading.total_volume_usd_24h}</strong>
                  </div>
                </div>
              </article>
              <article>
                <h5>{t("sections.holderMetrics")}</h5>
                {result.metrics.holders.top_10_ratio_percent !== null &&
                  result.metrics.holders.others_ratio_percent !== null && (
                    <div className="compareBlock">
                      <div className="compareHeader">
                        <span>Holder Distribution</span>
                        <span>
                          {result.metrics.holders.top_10_ratio_percent}% /{" "}
                          {result.metrics.holders.others_ratio_percent}%
                        </span>
                      </div>
                      <div className="compareBar">
                        <div
                          className="barTopHolders"
                          style={{
                            width: `${result.metrics.holders.top_10_ratio_percent}%`,
                          }}
                          title="Top 10 holders"
                        />
                        <div
                          className="barOthers"
                          style={{
                            width: `${result.metrics.holders.others_ratio_percent}%`,
                          }}
                          title="Other holders"
                        />
                      </div>
                      <div className="compareLegend">
                        <span className="legendTop">Top10</span>
                        <span className="legendOthers">Others</span>
                      </div>
                    </div>
                  )}
                <div className="kvList">
                  {result.metrics.holders.top_10_ratio_percent !== null && (
                    <div className="kvItem">
                      <span>Top 10 Ratio</span>
                      <strong>{result.metrics.holders.top_10_ratio_percent}%</strong>
                    </div>
                  )}
                  {result.metrics.holders.others_ratio_percent !== null && (
                    <div className="kvItem">
                      <span>Others Ratio</span>
                      <strong>{result.metrics.holders.others_ratio_percent}%</strong>
                    </div>
                  )}
                </div>
                <p>{result.metrics.holders.note}</p>
              </article>
              <article>
                <h5>{t("sections.lpMetrics")}</h5>
                <div className="kvList">
                  <div className="kvItem">
                    <span>Pair Count</span>
                    <strong>{result.metrics.lp.pair_count}</strong>
                  </div>
                  <div className="kvItem">
                    <span>Liquidity (USD)</span>
                    <strong>{result.metrics.lp.liquidity_usd}</strong>
                  </div>
                  {result.metrics.lp.lp_provider_count !== null && (
                    <div className="kvItem">
                      <span>LP Providers</span>
                      <strong>{result.metrics.lp.lp_provider_count}</strong>
                    </div>
                  )}
                  {result.metrics.lp.lp_locked_ratio_percent !== null && (
                    <div className="kvItem">
                      <span>LP Locked Ratio</span>
                      <strong>{result.metrics.lp.lp_locked_ratio_percent}%</strong>
                    </div>
                  )}
                </div>
              </article>
              <article>
                <h5>{t("sections.sourceCodeMetrics")}</h5>
                <p>
                  Public Source:{" "}
                  {result.metrics.source_code.is_public === null
                    ? "Unknown"
                    : result.metrics.source_code.is_public
                      ? "Yes"
                      : "No"}
                </p>
                <p>Status: {result.metrics.source_code.status}</p>
                <p>Platform: {result.metrics.source_code.source_platform ?? "N/A"}</p>
                {result.metrics.source_code.check_url && (
                  <p className="breakLine">
                    Explorer:{" "}
                    <a
                      className="breakLink"
                      href={result.metrics.source_code.check_url}
                      rel="noreferrer"
                      target="_blank"
                    >
                      {result.metrics.source_code.check_url}
                    </a>
                  </p>
                )}
                <p>{result.metrics.source_code.note}</p>
              </article>
            </div>

            {result.data_warnings.length > 0 && (
              <>
                <h4>{t("sections.dataWarnings")}</h4>
                <ul>
                  {result.data_warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              </>
            )}

            <h4>{t("sections.aiConclusion")}</h4>
            <p className="riskScore">Risk Score: {result.risk_score}</p>
            {renderMarkdown(result.summary)}
            {renderMarkdown(
              result.reasons
                .map((reason) =>
                  reason.trim().startsWith("-") ? reason : `- ${reason}`,
                )
                .join("\n"),
            )}
            {renderMarkdown(result.advice)}
          </div>
        ) : (
          <pre>{JSON.stringify(result, null, 2)}</pre>
        )}
      </section>

      {moduleKey === "blacklist" && (
        <section className="panel">
          <h3>Blacklist</h3>
          <pre>{JSON.stringify(blacklist, null, 2)}</pre>
        </section>
      )}

      <footer className="creatorFooter">
        {language === "zh-CN"
          ? "项目创作者：Telegram @kerryzheng"
          : "Project Creator: Telegram @kerryzheng"}
      </footer>
    </main>
  );
}

export default App;
