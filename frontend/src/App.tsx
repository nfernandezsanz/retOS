import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  Bot,
  CheckCircle2,
  Database,
  CircleStop,
  FolderPlus,
  FileSearch,
  KeyRound,
  Link2,
  LockKeyhole,
  Play,
  RefreshCw,
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
  domain_id: string | null;
  source_id: string | null;
  payload: Record<string, unknown>;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
};

type DomainRead = {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
};

type DocumentRead = {
  id: string;
  domain_id: string;
  source_id: string | null;
  external_id: string | null;
  title: string;
  content_hash: string;
  metadata: Record<string, unknown>;
  source_uri: string | null;
  size_bytes: number | null;
  created_at: string;
  updated_at: string;
};

type SourceKind = "upload" | "mount" | "url";

type SourceRead = {
  id: string;
  domain_id: string;
  kind: SourceKind;
  name: string;
  uri: string;
  created_at: string;
  updated_at: string;
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

type ProgressEvent = {
  id: number;
  event: string;
  data: Record<string, string | number | boolean | null>;
};

type LiveStatus = "disconnected" | "connecting" | "connected";

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

async function loadDomains(token: string): Promise<DomainRead[]> {
  return requestJson<DomainRead[]>("/domains", {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
}

async function createDomain(
  token: string,
  payload: { slug: string; name: string; description: string | null },
): Promise<DomainRead> {
  return requestJson<DomainRead>("/domains", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
}

async function loadDocuments(token: string, domainId: string): Promise<DocumentRead[]> {
  return requestJson<DocumentRead[]>(`/domains/${domainId}/documents`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
}

async function loadSources(token: string, domainId: string): Promise<SourceRead[]> {
  return requestJson<SourceRead[]>(`/domains/${domainId}/sources`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
}

async function loadJobs(token: string): Promise<JobRead[]> {
  return requestJson<JobRead[]>("/jobs?limit=12", {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
}

async function createSource(
  token: string,
  domainId: string,
  payload: { kind: SourceKind; name: string; uri: string },
): Promise<SourceRead> {
  return requestJson<SourceRead>(`/domains/${domainId}/sources`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
}

async function ingestText(
  token: string,
  domainId: string,
  payload: {
    source_id: string | null;
    title: string;
    text: string;
    source_uri: string;
    metadata: Record<string, string>;
    max_segment_tokens: number;
  },
): Promise<JobRead> {
  return requestJson<JobRead>(`/domains/${domainId}/ingestions/text`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
}

async function scanSource(token: string, sourceId: string): Promise<JobRead> {
  return requestJson<JobRead>(`/sources/${sourceId}/scan`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      run_inline: false,
      max_files: 500,
      max_bytes: 2000000,
      max_segment_tokens: 220,
      enable_ocr: true,
      max_ocr_pages: 20,
    }),
  });
}

async function rebuildIndex(token: string, domainId: string): Promise<JobRead> {
  return requestJson<JobRead>(`/domains/${domainId}/index/rebuild`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ run_inline: false }),
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

function parseSseFrames(buffer: string): { frames: string[]; rest: string } {
  const parts = buffer.split(/\n\n/);
  return {
    frames: parts.slice(0, -1),
    rest: parts.at(-1) ?? "",
  };
}

function parseProgressFrame(frame: string): ProgressEvent | null {
  const dataLines = frame
    .split(/\n/)
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.replace(/^data:\s?/, ""));
  if (dataLines.length === 0) {
    return null;
  }
  try {
    return JSON.parse(dataLines.join("\n")) as ProgressEvent;
  } catch {
    return null;
  }
}

function slugify(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 80);
}

function formatDateTime(value: string | null): string {
  if (!value) {
    return "Not recorded";
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

function summarizePayload(payload: Record<string, unknown>): string {
  const entries = Object.entries(payload).filter(([, value]) => value !== null && value !== "");
  if (entries.length === 0) {
    return "No payload";
  }
  return entries
    .slice(0, 4)
    .map(([key, value]) => `${key}: ${typeof value === "object" ? JSON.stringify(value) : String(value)}`)
    .join(" | ");
}

function App() {
  const [email, setEmail] = useState("admin@retos.dev");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_STORAGE_KEY) ?? "");
  const [catalog, setCatalog] = useState<ProviderCatalog | null>(null);
  const [isLoadingProvider, setIsLoadingProvider] = useState(false);
  const [providerError, setProviderError] = useState<string | null>(null);
  const [domains, setDomains] = useState<DomainRead[]>([]);
  const [selectedDomainId, setSelectedDomainId] = useState("");
  const [documents, setDocuments] = useState<DocumentRead[]>([]);
  const [sources, setSources] = useState<SourceRead[]>([]);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [isLoadingWorkspace, setIsLoadingWorkspace] = useState(false);
  const [isCreatingDomain, setIsCreatingDomain] = useState(false);
  const [isCreatingSource, setIsCreatingSource] = useState(false);
  const [sourceName, setSourceName] = useState("");
  const [sourceUri, setSourceUri] = useState("");
  const [sourceKind, setSourceKind] = useState<SourceKind>("mount");
  const [isQueueingScan, setIsQueueingScan] = useState(false);
  const [isQueueingIndex, setIsQueueingIndex] = useState(false);
  const [queuedJobs, setQueuedJobs] = useState<JobRead[]>([]);
  const [isIngestingText, setIsIngestingText] = useState(false);
  const [textTitle, setTextTitle] = useState("");
  const [textBody, setTextBody] = useState("");
  const [textSourceId, setTextSourceId] = useState("");
  const [domainSlug, setDomainSlug] = useState("");
  const [domainName, setDomainName] = useState("");
  const [domainDescription, setDomainDescription] = useState("");
  const [question, setQuestion] = useState("");
  const [queryResult, setQueryResult] = useState<AgentQueryResult | null>(null);
  const [queryJob, setQueryJob] = useState<JobRead | null>(null);
  const [isRunningQuery, setIsRunningQuery] = useState(false);
  const [queryError, setQueryError] = useState<string | null>(null);
  const [liveStatus, setLiveStatus] = useState<LiveStatus>("disconnected");
  const [liveError, setLiveError] = useState<string | null>(null);
  const [progressEvents, setProgressEvents] = useState<ProgressEvent[]>([]);
  const [jobFilter, setJobFilter] = useState("all");
  const liveAbortRef = useRef<AbortController | null>(null);

  const activeProviderLabel = useMemo(() => {
    if (!catalog) {
      return "Not connected";
    }
    return providerLabel(catalog.active.provider);
  }, [catalog]);

  const providerStatus = catalog?.active.can_call ? "Ready" : "Needs attention";

  const selectedDomain = useMemo(
    () => domains.find((domain) => domain.id === selectedDomainId) ?? null,
    [domains, selectedDomainId],
  );

  const activeJobs = useMemo(
    () => {
      const eventJobs = progressEvents.filter((event) => {
        const status = event.data.status;
        return status === "queued" || status === "running" || event.event.endsWith(".started");
      }).length;
      const recentJobs = queuedJobs.filter((job) => job.status === "queued" || job.status === "running")
        .length;
      return Math.max(eventJobs, recentJobs);
    },
    [progressEvents, queuedJobs],
  );

  const metrics = [
    { label: "Domains", value: domains.length.toString(), icon: Database },
    { label: "Documents", value: documents.length.toString(), icon: FileSearch },
    { label: "Active jobs", value: activeJobs.toString(), icon: Activity },
    { label: "Provider", value: activeProviderLabel, icon: Bot },
  ];

  const filteredJobs = useMemo(
    () =>
      jobFilter === "all"
        ? queuedJobs
        : queuedJobs.filter((job) => job.status === jobFilter || job.kind === jobFilter),
    [jobFilter, queuedJobs],
  );

  useEffect(() => {
    return () => {
      liveAbortRef.current?.abort();
    };
  }, []);

  async function refreshWorkspace(accessToken?: string, preferredDomainId?: string) {
    setIsLoadingWorkspace(true);
    setWorkspaceError(null);
    try {
      const adminToken = accessToken ?? (await getAdminToken());
      const nextDomains = await loadDomains(adminToken);
      setDomains(nextDomains);

      const nextSelectedDomainId =
        preferredDomainId && nextDomains.some((domain) => domain.id === preferredDomainId)
          ? preferredDomainId
          : selectedDomainId && nextDomains.some((domain) => domain.id === selectedDomainId)
            ? selectedDomainId
            : nextDomains[0]?.id ?? "";

      setSelectedDomainId(nextSelectedDomainId);
      if (nextSelectedDomainId) {
        const [nextDocuments, nextSources, nextJobs] = await Promise.all([
          loadDocuments(adminToken, nextSelectedDomainId),
          loadSources(adminToken, nextSelectedDomainId),
          loadJobs(adminToken),
        ]);
        setDocuments(nextDocuments);
        setSources(nextSources);
        setQueuedJobs(nextJobs);
      } else {
        setDocuments([]);
        setSources([]);
        setQueuedJobs(await loadJobs(adminToken));
      }
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Workspace refresh failed");
    } finally {
      setIsLoadingWorkspace(false);
    }
  }

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
      await refreshWorkspace(accessToken);
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

  async function handleDomainChange(nextDomainId: string) {
    setSelectedDomainId(nextDomainId);
    setQueryResult(null);
    setQueryJob(null);
    setWorkspaceError(null);
    setTextSourceId("");
    if (!nextDomainId) {
      setDocuments([]);
      setSources([]);
      return;
    }
    setIsLoadingWorkspace(true);
    try {
      const accessToken = await getAdminToken();
      const [nextDocuments, nextSources, nextJobs] = await Promise.all([
        loadDocuments(accessToken, nextDomainId),
        loadSources(accessToken, nextDomainId),
        loadJobs(accessToken),
      ]);
      setDocuments(nextDocuments);
      setSources(nextSources);
      setQueuedJobs(nextJobs);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Document refresh failed");
    } finally {
      setIsLoadingWorkspace(false);
    }
  }

  async function handleCreateDomain(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError(null);
    setIsCreatingDomain(true);
    try {
      const slug = domainSlug.trim().toLowerCase();
      const name = domainName.trim();
      if (!slug || !name) {
        throw new Error("Domain slug and name are required");
      }
      const accessToken = await getAdminToken();
      const domain = await createDomain(accessToken, {
        slug,
        name,
        description: domainDescription.trim() || null,
      });
      setDomainSlug("");
      setDomainName("");
      setDomainDescription("");
      await refreshWorkspace(accessToken, domain.id);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Domain creation failed");
    } finally {
      setIsCreatingDomain(false);
    }
  }

  async function handleCreateSource(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError(null);
    setIsCreatingSource(true);
    try {
      if (!selectedDomainId) {
        throw new Error("Select a domain before adding a source");
      }
      const name = sourceName.trim();
      const uri = sourceUri.trim();
      if (!name || !uri) {
        throw new Error("Source name and URI are required");
      }
      const accessToken = await getAdminToken();
      const source = await createSource(accessToken, selectedDomainId, {
        kind: sourceKind,
        name,
        uri,
      });
      setSources((current) => [...current, source]);
      setSourceName("");
      setSourceUri("");
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Source creation failed");
    } finally {
      setIsCreatingSource(false);
    }
  }

  async function handleIngestText(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError(null);
    setIsIngestingText(true);
    try {
      if (!selectedDomainId) {
        throw new Error("Select a domain before ingesting text");
      }
      const title = textTitle.trim();
      const text = textBody.trim();
      if (!title || !text) {
        throw new Error("Text title and content are required");
      }
      const accessToken = await getAdminToken();
      const sourceUri = `inline://${selectedDomain?.slug ?? selectedDomainId}/${slugify(title) || "note"}`;
      const job = await ingestText(accessToken, selectedDomainId, {
        source_id: textSourceId || null,
        title,
        text,
        source_uri: sourceUri,
        metadata: { ingestion: "console" },
        max_segment_tokens: 220,
      });
      setQueuedJobs((current) => [job, ...current].slice(0, 6));
      setTextTitle("");
      setTextBody("");
      const [nextDocuments, nextJobs] = await Promise.all([
        loadDocuments(accessToken, selectedDomainId),
        loadJobs(accessToken),
      ]);
      setDocuments(nextDocuments);
      setQueuedJobs(nextJobs.length > 0 ? nextJobs : [job]);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Text ingestion failed");
    } finally {
      setIsIngestingText(false);
    }
  }

  async function handleScanSource(sourceId: string) {
    setWorkspaceError(null);
    setIsQueueingScan(true);
    try {
      const accessToken = await getAdminToken();
      const job = await scanSource(accessToken, sourceId);
      setQueuedJobs((current) => [job, ...current].slice(0, 6));
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Source scan failed");
    } finally {
      setIsQueueingScan(false);
    }
  }

  async function handleRebuildIndex() {
    setWorkspaceError(null);
    setIsQueueingIndex(true);
    try {
      if (!selectedDomainId) {
        throw new Error("Select a domain before rebuilding the index");
      }
      const accessToken = await getAdminToken();
      const job = await rebuildIndex(accessToken, selectedDomainId);
      setQueuedJobs((current) => [job, ...current].slice(0, 6));
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Index rebuild failed");
    } finally {
      setIsQueueingIndex(false);
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
      const trimmedQuestion = question.trim();
      if (!selectedDomainId || !trimmedQuestion) {
        throw new Error("Select a domain and write a question");
      }
      const accessToken = await getAdminToken();
      const response = await runAgentQuery(accessToken, selectedDomainId, trimmedQuestion);
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

  async function handleConnectLiveUpdates() {
    if (liveStatus === "connected" || liveStatus === "connecting") {
      liveAbortRef.current?.abort();
      liveAbortRef.current = null;
      setLiveStatus("disconnected");
      return;
    }

    setLiveStatus("connecting");
    setLiveError(null);
    const controller = new AbortController();
    liveAbortRef.current = controller;
    try {
      const accessToken = await getAdminToken();
      if (controller.signal.aborted) {
        return;
      }
      const response = await fetch(`${API_BASE_URL}/events/progress`, {
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
        signal: controller.signal,
      });
      if (!response.ok || !response.body) {
        throw new Error(`Live updates failed with ${response.status}`);
      }

      setLiveStatus("connected");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          break;
        }
        buffer += decoder.decode(value, { stream: true });
        const parsed = parseSseFrames(buffer);
        buffer = parsed.rest;
        const nextEvents = parsed.frames
          .map(parseProgressFrame)
          .filter((event): event is ProgressEvent => event !== null);
        if (nextEvents.length > 0) {
          setProgressEvents((current) => [...current, ...nextEvents].slice(-8));
        }
      }

      if (!controller.signal.aborted) {
        setLiveStatus("disconnected");
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      setLiveStatus("disconnected");
      setLiveError(error instanceof Error ? error.message : "Live updates failed");
    } finally {
      if (liveAbortRef.current === controller) {
        liveAbortRef.current = null;
      }
    }
  }

  function handleDisconnect() {
    liveAbortRef.current?.abort();
    liveAbortRef.current = null;
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    setToken("");
    setCatalog(null);
    setProviderError(null);
    setQueryResult(null);
    setQueryJob(null);
    setDomains([]);
    setSelectedDomainId("");
    setDocuments([]);
    setSources([]);
    setWorkspaceError(null);
    setLiveStatus("disconnected");
    setLiveError(null);
    setProgressEvents([]);
    setQueuedJobs([]);
    setTextTitle("");
    setTextBody("");
    setTextSourceId("");
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
          <button
            type="button"
            className="primary-action"
            disabled={isLoadingWorkspace}
            onClick={() => void refreshWorkspace()}
          >
            <RefreshCw aria-hidden="true" />
            {isLoadingWorkspace ? "Refreshing workspace" : "Refresh workspace"}
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
                <p className="eyebrow">Knowledge base</p>
                <h2>Domains and documents</h2>
              </div>
              <span className="status-pill">{selectedDomain ? selectedDomain.slug : "No domain"}</span>
            </div>
            <form className="domain-form" onSubmit={handleCreateDomain}>
              <label>
                <span>Slug</span>
                <input
                  placeholder="legal-research"
                  value={domainSlug}
                  onChange={(event) => setDomainSlug(event.target.value)}
                />
              </label>
              <label>
                <span>Name</span>
                <input
                  placeholder="Legal research"
                  value={domainName}
                  onChange={(event) => setDomainName(event.target.value)}
                />
              </label>
              <label className="span-two">
                <span>Description</span>
                <input
                  placeholder="Purpose, scope, or data boundary"
                  value={domainDescription}
                  onChange={(event) => setDomainDescription(event.target.value)}
                />
              </label>
              <button className="secondary-action" disabled={isCreatingDomain} type="submit">
                <FolderPlus aria-hidden="true" />
                {isCreatingDomain ? "Creating domain" : "Create domain"}
              </button>
            </form>
            <div className="domain-toolbar">
              <label>
                <span>Active domain</span>
                <select
                  value={selectedDomainId}
                  onChange={(event) => void handleDomainChange(event.target.value)}
                >
                  <option value="">Select a domain</option>
                  {domains.map((domain) => (
                    <option key={domain.id} value={domain.id}>
                      {domain.name}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className="ghost-action"
                disabled={isLoadingWorkspace}
                type="button"
                onClick={() => void refreshWorkspace()}
              >
                <RefreshCw aria-hidden="true" />
                {isLoadingWorkspace ? "Refreshing" : "Refresh"}
              </button>
            </div>
            {workspaceError ? (
              <p className="inline-error" role="alert">
                {workspaceError}
              </p>
            ) : null}
            <div className="document-list" aria-label="Domain documents">
              {documents.map((document) => (
                <article className="document-row" key={document.id}>
                  <div>
                    <strong>{document.title}</strong>
                    <span>{document.source_uri ?? document.external_id ?? document.id}</span>
                  </div>
                  <span className="badge muted">{document.content_hash.slice(0, 10)}</span>
                </article>
              ))}
              {selectedDomain && documents.length === 0 ? (
                <div className="empty-state compact">
                  <FileSearch aria-hidden="true" />
                  <p>No documents registered for this domain yet.</p>
                </div>
              ) : null}
              {!selectedDomain ? (
                <div className="empty-state compact">
                  <Database aria-hidden="true" />
                  <p>Create or select a domain to inspect documents and run grounded queries.</p>
                </div>
              ) : null}
            </div>
            <section className="source-workspace" aria-label="Domain sources">
              <div className="section-heading">
                <h3>Sources</h3>
                <button
                  className="ghost-action"
                  disabled={!selectedDomainId || isQueueingIndex}
                  type="button"
                  onClick={() => void handleRebuildIndex()}
                >
                  <RefreshCw aria-hidden="true" />
                  {isQueueingIndex ? "Queueing index" : "Rebuild index"}
                </button>
              </div>
              <form className="source-form" onSubmit={handleCreateSource}>
                <label>
                  <span>Kind</span>
                  <select
                    value={sourceKind}
                    onChange={(event) => setSourceKind(event.target.value as SourceKind)}
                  >
                    <option value="mount">Mount</option>
                    <option value="upload">Upload</option>
                    <option value="url">URL</option>
                  </select>
                </label>
                <label>
                  <span>Name</span>
                  <input
                    placeholder="Research corpus"
                    value={sourceName}
                    onChange={(event) => setSourceName(event.target.value)}
                  />
                </label>
                <label className="span-two">
                  <span>URI</span>
                  <input
                    placeholder="file:///corpus/research"
                    value={sourceUri}
                    onChange={(event) => setSourceUri(event.target.value)}
                  />
                </label>
                <button
                  className="secondary-action"
                  disabled={!selectedDomainId || isCreatingSource}
                  type="submit"
                >
                  <FolderPlus aria-hidden="true" />
                  {isCreatingSource ? "Adding source" : "Add source"}
                </button>
              </form>
              <div className="source-list">
                {sources.map((source) => (
                  <article className="source-row" key={source.id}>
                    <div>
                      <strong>{source.name}</strong>
                      <span>{source.uri}</span>
                    </div>
                    <span className="badge muted">{source.kind}</span>
                    <button
                      className="ghost-action"
                      disabled={source.kind !== "mount" || isQueueingScan}
                      type="button"
                      onClick={() => void handleScanSource(source.id)}
                    >
                      <Play aria-hidden="true" />
                      {isQueueingScan ? "Queueing" : "Scan"}
                    </button>
                  </article>
                ))}
                {selectedDomain && sources.length === 0 ? (
                  <div className="empty-state compact">
                    <Database aria-hidden="true" />
                    <p>Add a mounted source to scan files into this domain.</p>
                  </div>
                ) : null}
              </div>
            </section>
            <section className="text-ingestion" aria-label="Text ingestion">
              <div className="section-heading">
                <h3>Text ingestion</h3>
              </div>
              <form className="text-ingestion-form" onSubmit={handleIngestText}>
                <label>
                  <span>Title</span>
                  <input
                    placeholder="Research note"
                    value={textTitle}
                    onChange={(event) => setTextTitle(event.target.value)}
                  />
                </label>
                <label>
                  <span>Source</span>
                  <select
                    value={textSourceId}
                    onChange={(event) => setTextSourceId(event.target.value)}
                  >
                    <option value="">No source</option>
                    {sources.map((source) => (
                      <option key={source.id} value={source.id}>
                        {source.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="span-two">
                  <span>Text</span>
                  <textarea
                    placeholder="Paste local fixture text, notes, transcripts, or extracted content."
                    value={textBody}
                    onChange={(event) => setTextBody(event.target.value)}
                  />
                </label>
                <button
                  className="secondary-action"
                  disabled={!selectedDomainId || isIngestingText}
                  type="submit"
                >
                  <FileSearch aria-hidden="true" />
                  {isIngestingText ? "Queueing text" : "Queue text ingestion"}
                </button>
              </form>
            </section>
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
              <div className="selected-domain">
                <span>Active domain</span>
                <strong>{selectedDomain ? selectedDomain.name : "Select a domain first"}</strong>
              </div>
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

          <article className="panel wide">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Pipeline</p>
                <h2>Processing timeline</h2>
              </div>
              <span className={liveStatus === "connected" ? "status-pill local" : "status-pill"}>
                {liveStatus === "connected" ? "Live" : "Offline"}
              </span>
            </div>
            <div className="live-toolbar">
              <button
                className={liveStatus === "connected" ? "ghost-action" : "secondary-action"}
                type="button"
                onClick={() => void handleConnectLiveUpdates()}
              >
                {liveStatus === "connected" ? (
                  <CircleStop aria-hidden="true" />
                ) : (
                  <RefreshCw aria-hidden="true" />
                )}
                {liveStatus === "connecting"
                  ? "Connecting"
                  : liveStatus === "connected"
                    ? "Disconnect live updates"
                    : "Connect live updates"}
              </button>
              {liveError ? (
                <p className="inline-error" role="alert">
                  {liveError}
                </p>
              ) : null}
            </div>
            <ol className="timeline" aria-live="polite">
              {pipelineSteps.map((step) => (
                <li key={step.label} className={step.state}>
                  <strong>{step.label}</strong>
                  <span>{step.value}</span>
                </li>
              ))}
            </ol>
            <section className="event-ledger" aria-label="Live progress events" aria-live="polite">
              {queuedJobs.length > 0 ? (
                <div className="queued-jobs" aria-label="Queued jobs">
                  {queuedJobs.map((job) => (
                    <span className="badge muted" key={job.id}>
                      {job.kind} {job.status}
                    </span>
                  ))}
                </div>
              ) : null}
              {progressEvents.map((event) => (
                <article className="event-row" key={`${event.id}-${event.event}`}>
                  <span className="event-id">#{event.id}</span>
                  <div>
                    <strong>{event.event}</strong>
                    <span>{String(event.data.message ?? event.data.job_id ?? "Progress update")}</span>
                  </div>
                </article>
              ))}
              {progressEvents.length === 0 ? (
                <div className="empty-state compact">
                  <Activity aria-hidden="true" />
                  <p>Connect live updates to watch job and ingestion progress as events arrive.</p>
                </div>
              ) : null}
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
                <h2>Jobs and evidence ledger</h2>
              </div>
              <span className="status-pill">{queuedJobs.length} recent jobs</span>
            </div>
            <div className="audit-toolbar">
              <label>
                <span>Filter jobs</span>
                <select value={jobFilter} onChange={(event) => setJobFilter(event.target.value)}>
                  <option value="all">All jobs</option>
                  <option value="queued">Queued</option>
                  <option value="running">Running</option>
                  <option value="succeeded">Succeeded</option>
                  <option value="failed">Failed</option>
                  <option value="ingest.source">Ingestion</option>
                  <option value="index.domain">Indexing</option>
                  <option value="agent.query">Agent queries</option>
                </select>
              </label>
              <button
                className="ghost-action"
                disabled={isLoadingWorkspace}
                type="button"
                onClick={() => void refreshWorkspace()}
              >
                <RefreshCw aria-hidden="true" />
                Refresh jobs
              </button>
            </div>
            <div className="job-ledger" aria-label="Recent jobs">
              {filteredJobs.map((job) => (
                <article className="job-row" key={job.id}>
                  <div className="job-row-main">
                    <span className={`badge ${job.status === "failed" ? "warning" : "muted"}`}>
                      {job.status}
                    </span>
                    <div>
                      <strong>{job.kind}</strong>
                      <span>{job.id}</span>
                    </div>
                  </div>
                  <div className="job-row-grid">
                    <div>
                      <span>Domain</span>
                      <strong>{job.domain_id ?? "none"}</strong>
                    </div>
                    <div>
                      <span>Source</span>
                      <strong>{job.source_id ?? "none"}</strong>
                    </div>
                    <div>
                      <span>Created</span>
                      <strong>{formatDateTime(job.created_at)}</strong>
                    </div>
                    <div>
                      <span>Completed</span>
                      <strong>{formatDateTime(job.completed_at)}</strong>
                    </div>
                  </div>
                  {job.error ? (
                    <p className="inline-error" role="alert">
                      {job.error}
                    </p>
                  ) : null}
                  <p className="payload-summary">{summarizePayload(job.payload)}</p>
                </article>
              ))}
              {filteredJobs.length === 0 ? (
                <div className="empty-state compact">
                  <LockKeyhole aria-hidden="true" />
                  <p>No jobs match this filter yet.</p>
                </div>
              ) : null}
            </div>
          </article>
        </section>
      </section>
    </main>
  );
}

export default App;
