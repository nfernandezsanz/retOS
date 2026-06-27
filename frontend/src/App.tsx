import { useMemo, useState } from "react";
import {
  Activity,
  Bot,
  CheckCircle2,
  Database,
  FileSearch,
  KeyRound,
  Link2,
  LockKeyhole,
  Radio,
  Send,
  ServerCog,
  ShieldAlert,
} from "lucide-react";
import "./styles.css";

type ProviderName = "fake" | "local" | "openai" | "anthropic" | "google" | "openrouter" | "azure";

type ProviderProfile = {
  name: ProviderName;
  label: string;
  default_model: string;
  configured: boolean;
  enabled: boolean;
  paid: boolean;
  reason: string | null;
  base_url: string | null;
};

type ActiveProvider = {
  provider: ProviderName;
  model: string;
  paid: boolean;
  can_call: boolean;
  reason: string | null;
};

type ProviderCatalog = {
  active: ActiveProvider;
  providers: ProviderProfile[];
};

type TokenResponse = {
  access_token: string;
  token_type: "bearer";
};

type JobRead = {
  id: string;
  kind: string;
  status: string;
  payload: Record<string, unknown>;
};

type AgentCitation = {
  segment_id: string;
  document_id: string;
  document_version_id: string;
  title: string;
  anchor: string | null;
  score: number;
  text: string;
};

type AgentQueryResult = {
  answer: string;
  provider: string;
  model: string;
  citations: AgentCitation[];
};

type AgentQueryResponse = {
  job: JobRead;
  result: AgentQueryResult | null;
};

const API_BASE_URL = import.meta.env.VITE_RETOS_API_URL ?? "http://localhost:8000";
const TOKEN_STORAGE_KEY = "retos.adminToken";

const pipelineSteps = [
  { label: "Scan", value: "Discover mounted files and uploads", state: "ready" },
  { label: "Hash", value: "Create deterministic content identities", state: "ready" },
  { label: "OCR", value: "Extract text from scanned pages locally", state: "waiting" },
  { label: "Index", value: "Build rebuildable Tantivy BM25 projections", state: "waiting" },
];

async function requestJson<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });
  if (!response.ok) {
    throw new Error(`Request failed with ${response.status}`);
  }
  return (await response.json()) as T;
}

async function login(email: string, password: string): Promise<string> {
  const body = JSON.stringify({ email, password });
  const token = await requestJson<TokenResponse>("/auth/login", {
    method: "POST",
    body,
  });
  return token.access_token;
}

async function loadProviderCatalog(token: string): Promise<ProviderCatalog> {
  return requestJson<ProviderCatalog>("/llm/providers", {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
}

async function runAgentQuery(
  token: string,
  domainId: string,
  question: string,
): Promise<AgentQueryResponse> {
  return requestJson<AgentQueryResponse>(`/domains/${domainId}/queries`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      question,
      limit: 5,
      run_inline: true,
    }),
  });
}

function providerLabel(name: ProviderName): string {
  if (name === "local") {
    return "Ollama";
  }
  if (name === "fake") {
    return "Fake";
  }
  return name.charAt(0).toUpperCase() + name.slice(1);
}

function App() {
  const [email, setEmail] = useState("admin@retos.dev");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_STORAGE_KEY) ?? "");
  const [catalog, setCatalog] = useState<ProviderCatalog | null>(null);
  const [isLoadingProvider, setIsLoadingProvider] = useState(false);
  const [providerError, setProviderError] = useState<string | null>(null);
  const [domainId, setDomainId] = useState("");
  const [question, setQuestion] = useState("");
  const [queryResult, setQueryResult] = useState<AgentQueryResult | null>(null);
  const [queryJob, setQueryJob] = useState<JobRead | null>(null);
  const [isRunningQuery, setIsRunningQuery] = useState(false);
  const [queryError, setQueryError] = useState<string | null>(null);

  const activeProviderLabel = useMemo(() => {
    if (!catalog) {
      return "Not connected";
    }
    return providerLabel(catalog.active.provider);
  }, [catalog]);

  const providerStatus = catalog?.active.can_call ? "Ready" : "Needs attention";

  const metrics = [
    { label: "Domains", value: "0", icon: Database },
    { label: "Documents", value: "0", icon: FileSearch },
    { label: "Active jobs", value: "0", icon: Activity },
    { label: "Provider", value: activeProviderLabel, icon: Bot },
  ];

  async function handleProviderLogin(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsLoadingProvider(true);
    setProviderError(null);
    try {
      const accessToken = token || (await login(email, password));
      localStorage.setItem(TOKEN_STORAGE_KEY, accessToken);
      setToken(accessToken);
      const nextCatalog = await loadProviderCatalog(accessToken);
      setCatalog(nextCatalog);
      setPassword("");
    } catch (error) {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
      setToken("");
      setCatalog(null);
      setProviderError(error instanceof Error ? error.message : "Provider catalog failed");
    } finally {
      setIsLoadingProvider(false);
    }
  }

  async function getAdminToken(): Promise<string> {
    if (token) {
      return token;
    }
    const accessToken = await login(email, password);
    localStorage.setItem(TOKEN_STORAGE_KEY, accessToken);
    setToken(accessToken);
    return accessToken;
  }

  async function handleQuerySubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsRunningQuery(true);
    setQueryError(null);
    setQueryResult(null);
    setQueryJob(null);
    try {
      const trimmedDomainId = domainId.trim();
      const trimmedQuestion = question.trim();
      if (!trimmedDomainId || !trimmedQuestion) {
        throw new Error("Domain ID and question are required");
      }
      const accessToken = await getAdminToken();
      const response = await runAgentQuery(accessToken, trimmedDomainId, trimmedQuestion);
      setQueryJob(response.job);
      if (!response.result) {
        throw new Error("Query was queued; open Jobs to inspect worker progress");
      }
      setQueryResult(response.result);
    } catch (error) {
      setQueryError(error instanceof Error ? error.message : "Agent query failed");
    } finally {
      setIsRunningQuery(false);
    }
  }

  function handleDisconnect() {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    setToken("");
    setCatalog(null);
    setProviderError(null);
    setQueryResult(null);
    setQueryJob(null);
  }

  return (
    <main className="shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand">
          <ServerCog aria-hidden="true" />
          <span>RetOS</span>
        </div>
        <nav>
          <a href="#overview">Overview</a>
          <a href="#documents">Documents</a>
          <a href="#queries">Queries</a>
          <a href="#audit">Audit</a>
          <a href="#admin">Admin</a>
        </nav>
      </aside>

      <section className="workspace" id="overview">
        <header className="topbar">
          <div>
            <p className="eyebrow">Local-first research console</p>
            <h1>Auditable document investigation</h1>
          </div>
          <button type="button" className="primary-action">
            <Radio aria-hidden="true" />
            Connect live updates
          </button>
        </header>

        <section className="metrics" aria-label="System metrics">
          {metrics.map((metric) => {
            const Icon = metric.icon;
            return (
              <article className="metric" key={metric.label}>
                <Icon aria-hidden="true" />
                <div>
                  <span>{metric.label}</span>
                  <strong>{metric.value}</strong>
                </div>
              </article>
            );
          })}
        </section>

        <section className="content-grid">
          <article className="panel" id="documents">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Pipeline</p>
                <h2>Processing timeline</h2>
              </div>
              <span className="status-pill">Idle</span>
            </div>
            <ol className="timeline" aria-live="polite">
              {pipelineSteps.map((step) => (
                <li key={step.label} className={step.state}>
                  <strong>{step.label}</strong>
                  <span>{step.value}</span>
                </li>
              ))}
            </ol>
          </article>

          <article className="panel" id="queries">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Research</p>
                <h2>Query workspace</h2>
              </div>
              <span className="status-pill local">Local model</span>
            </div>
            <form className="query-form" onSubmit={handleQuerySubmit}>
              <label className="query-box compact-field">
                <span>Domain ID</span>
                <input
                  placeholder="Paste a domain UUID"
                  value={domainId}
                  onChange={(event) => setDomainId(event.target.value)}
                />
              </label>
              <label className="query-box">
                <span>Question</span>
                <textarea
                  placeholder="Ask a grounded question about the indexed corpus."
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                />
              </label>
              <button className="secondary-action" disabled={isRunningQuery} type="submit">
                <Send aria-hidden="true" />
                {isRunningQuery ? "Running query" : "Run grounded query"}
              </button>
              {queryError ? (
                <p className="inline-error" role="alert">
                  {queryError}
                </p>
              ) : null}
            </form>
            <section className="query-result" aria-live="polite">
              {queryResult ? (
                <>
                  <div className="result-meta">
                    <span>Job {queryJob?.status ?? "unknown"}</span>
                    <span>{queryResult.model}</span>
                    <span>{queryResult.citations.length} citations</span>
                  </div>
                  <p>{queryResult.answer}</p>
                  <div className="citation-list" aria-label="Query citations">
                    {queryResult.citations.map((citation) => (
                      <article className="citation-row" key={citation.segment_id}>
                        <div>
                          <strong>{citation.title}</strong>
                          <span>{citation.anchor ?? "No anchor"}</span>
                        </div>
                        <p>{citation.text}</p>
                        <span className="badge muted">
                          <Link2 aria-hidden="true" />
                          {citation.segment_id.slice(0, 8)}
                        </span>
                      </article>
                    ))}
                  </div>
                </>
              ) : (
                <div className="empty-state compact">
                  <Bot aria-hidden="true" />
                  <p>Run a query to inspect the answer, citations, provider, and job status.</p>
                </div>
              )}
            </section>
          </article>

          <article className="panel wide" id="admin">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Admin</p>
                <h2>LLM providers</h2>
              </div>
              <span className={catalog?.active.can_call ? "status-pill local" : "status-pill"}>
                {providerStatus}
              </span>
            </div>

            <div className="admin-grid">
              <form className="provider-login" onSubmit={handleProviderLogin}>
                <label>
                  <span>Email</span>
                  <input
                    autoComplete="username"
                    type="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                  />
                </label>
                <label>
                  <span>Password</span>
                  <input
                    autoComplete="current-password"
                    disabled={Boolean(token)}
                    type="password"
                    value={token ? "stored-session" : password}
                    onChange={(event) => setPassword(event.target.value)}
                  />
                </label>
                <div className="button-row">
                  <button className="secondary-action" disabled={isLoadingProvider} type="submit">
                    <KeyRound aria-hidden="true" />
                    {isLoadingProvider ? "Loading providers" : "Load providers"}
                  </button>
                  {token ? (
                    <button className="ghost-action" type="button" onClick={handleDisconnect}>
                      Disconnect
                    </button>
                  ) : null}
                </div>
                {providerError ? (
                  <p className="inline-error" role="alert">
                    {providerError}
                  </p>
                ) : null}
              </form>

              <section className="provider-summary" aria-live="polite">
                <div>
                  <span>Active runtime</span>
                  <strong>{catalog ? catalog.active.model : "Connect admin session"}</strong>
                </div>
                <div>
                  <span>Cost guardrail</span>
                  <strong>{catalog?.active.paid ? "Paid provider" : "No paid calls"}</strong>
                </div>
                <div>
                  <span>Status</span>
                  <strong>{catalog ? providerStatus : "Waiting for login"}</strong>
                </div>
              </section>
            </div>

            <div className="provider-list" aria-label="Available LLM providers">
              {(catalog?.providers ?? []).map((provider) => (
                <article className="provider-row" key={provider.name}>
                  <div>
                    <strong>{provider.label}</strong>
                    <span>{provider.default_model}</span>
                  </div>
                  <div className="provider-badges">
                    <span className={provider.paid ? "badge warning" : "badge success"}>
                      {provider.paid ? "Paid" : "Local/test"}
                    </span>
                    <span className={provider.enabled ? "badge success" : "badge muted"}>
                      {provider.enabled ? "Enabled" : "Blocked"}
                    </span>
                  </div>
                  {provider.enabled ? (
                    <CheckCircle2 aria-label="Provider enabled" className="row-icon success" />
                  ) : (
                    <ShieldAlert aria-label={provider.reason ?? "Provider blocked"} className="row-icon" />
                  )}
                </article>
              ))}
              {!catalog ? (
                <div className="empty-state compact">
                  <LockKeyhole aria-hidden="true" />
                  <p>Load the provider catalog to inspect local and paid runtime readiness.</p>
                </div>
              ) : null}
            </div>
          </article>

          <article className="panel wide" id="audit">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Audit</p>
                <h2>Evidence ledger</h2>
              </div>
              <span className="status-pill">No runs yet</span>
            </div>
            <div className="empty-state">
              <LockKeyhole aria-hidden="true" />
              <p>
                Agent runs will appear here with tool calls, cited segments, answer hashes, and
                budget usage.
              </p>
            </div>
          </article>
        </section>
      </section>
    </main>
  );
}

export default App;
