import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  Archive,
  Bot,
  Check,
  CheckCircle2,
  Database,
  CircleStop,
  Download,
  Eye,
  GitCompare,
  RotateCcw,
  FolderPlus,
  FileSearch,
  History,
  KeyRound,
  Link2,
  LockKeyhole,
  Pencil,
  Play,
  RefreshCw,
  Send,
  ServerCog,
  ShieldAlert,
  Power,
  UserPlus,
  Users,
  X,
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

type AdminUserRead = {
  id: string;
  email: string;
  roles: string[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

type AdminUserDomainGrantRead = {
  id: string;
  admin_user_id: string;
  domain_id: string;
  created_at: string;
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
  source_uri?: string | null;
  size_bytes?: number | null;
  archived_at: string | null;
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

type AgentNeighborContext = {
  segment_id: string;
  source_segment_id: string;
  document_id: string;
  document_version_id: string;
  title: string;
  anchor: string | null;
  ordinal: number;
  distance: number;
  text: string;
  token_count: number;
};

type AgentBudgetUsage = {
  budget: {
    max_searches: number;
    max_citations: number;
    max_evidence_tokens: number;
    max_runtime_seconds: number;
  };
  search_count: number;
  citation_count: number;
  evidence_tokens: number;
  runtime_ms: number;
  within_budget: boolean;
};

type AgentEvidenceRoute = {
  coverage_level: string;
  segment_count: number;
  document_count: number;
  anchor_count: number;
  multi_document: boolean;
  has_neighbor_context: boolean;
  warnings: string[];
  documents: {
    document_id: string;
    title: string;
    segment_ids: string[];
    anchors: string[];
  }[];
};

type AgentMultiHopAudit = {
  checked: boolean;
  requires_multi_hop: boolean;
  status: string;
  document_count: number;
  bridge_terms: string[];
  warnings: string[];
};

type AgentQueryResult = {
  answer: string;
  provider: string;
  model: string;
  runtime: string;
  evidence_audit?: {
    grounded: boolean;
    cited_segment_ids: string[];
    unreferenced_citation_ids: string[];
  } | null;
  contradiction_audit?: {
    checked: boolean;
    conflict_count: number;
    findings: {
      segment_ids: string[];
      shared_terms: string[];
      summary: string;
    }[];
  } | null;
  multi_hop_audit?: AgentMultiHopAudit | null;
  evidence_route?: AgentEvidenceRoute | null;
  usage: AgentBudgetUsage;
  citations: AgentCitation[];
  neighbor_context?: AgentNeighborContext[];
};

type AgentQueryResponse = {
  job: JobRead;
  result: AgentQueryResult | null;
};

function evidenceAuditFor(result: AgentQueryResult) {
  return (
    result.evidence_audit ?? {
      grounded: result.citations.length === 0,
      cited_segment_ids: [],
      unreferenced_citation_ids: result.citations.map((citation) => citation.segment_id),
    }
  );
}

function contradictionAuditFor(result: AgentQueryResult) {
  return (
    result.contradiction_audit ?? {
      checked: false,
      conflict_count: 0,
      findings: [],
    }
  );
}

function multiHopAuditFor(result: AgentQueryResult): AgentMultiHopAudit {
  const documentCount = new Set(result.citations.map((citation) => citation.document_id)).size;
  return (
    result.multi_hop_audit ?? {
      checked: false,
      requires_multi_hop: false,
      status: documentCount > 1 ? "opportunistic_multi_document" : "not_required",
      document_count: documentCount,
      bridge_terms: [],
      warnings: [],
    }
  );
}

function evidenceRouteFor(result: AgentQueryResult): AgentEvidenceRoute {
  return (
    result.evidence_route ?? {
      coverage_level:
        result.citations.length === 0
          ? "no_evidence"
          : result.citations.length === 1
            ? "single_segment"
            : "single_document",
      segment_count: result.citations.length,
      document_count: new Set(result.citations.map((citation) => citation.document_id)).size,
      anchor_count: new Set(
        result.citations
          .filter((citation) => Boolean(citation.anchor))
          .map((citation) => `${citation.document_id}:${citation.anchor}`),
      ).size,
      multi_document:
        new Set(result.citations.map((citation) => citation.document_id)).size > 1,
      has_neighbor_context: (result.neighbor_context ?? []).length > 0,
      warnings: result.citations.length === 0 ? ["no_citations"] : [],
      documents: [],
    }
  );
}

type EvalMetrics = Record<string, number>;

type EvalCaseResult = {
  case_id: string;
  question?: string;
  passed: boolean;
  retrieval_recall?: boolean;
  citation_validity?: boolean;
  grounded_answer?: boolean;
  abstention?: boolean;
  budget_compliance?: boolean;
  answer?: string;
  citations?: Record<string, unknown>[];
  character_error_rate?: number;
  word_error_rate?: number;
  failures: string[];
};

type EvalReport = {
  suite_name: string;
  passed: boolean;
  case_count: number;
  metadata?: Record<string, unknown>;
  metrics: EvalMetrics;
  cases: EvalCaseResult[];
};

type EvalReportPaths = {
  json: string;
  markdown: string;
};

type EvalRunResponse = {
  job: JobRead;
  report: EvalReport;
  report_paths: EvalReportPaths | null;
};

type EvalRunRead = {
  job: JobRead;
  report: EvalReport | null;
};

type EvalRunSummary = {
  job_id: string;
  suite_name: string;
  passed: boolean;
  case_count: number;
  completed_at: string | null;
};

type EvalMetricComparison = {
  name: string;
  baseline: number;
  candidate: number;
  delta: number;
};

type EvalRunComparison = {
  baseline: EvalRunSummary;
  candidate: EvalRunSummary;
  metrics: EvalMetricComparison[];
  average_delta: number;
  status: string;
};

type EvalTrendPoint = {
  job_id: string;
  suite_name: string;
  passed: boolean;
  case_count: number;
  completed_at: string | null;
  metrics: EvalMetrics;
};

type EvalMetricTrend = {
  name: string;
  first: number;
  latest: number;
  delta: number;
  minimum: number;
  maximum: number;
  average: number;
  direction: string;
};

type EvalSuiteTrend = {
  suite_name: string;
  run_count: number;
  pass_rate: number;
  latest: EvalRunSummary;
  metrics: EvalMetricTrend[];
  points: EvalTrendPoint[];
};

type ProgressEvent = {
  id: string;
  event: string;
  data: Record<string, unknown>;
};

type DocumentChangeRead = {
  field: string;
  before: unknown;
  after: unknown;
};

type DocumentHistoryEventRead = {
  id: string;
  occurred_at: string;
  actor: string;
  event_type: string;
  changes: DocumentChangeRead[];
  payload: Record<string, unknown>;
};

type DocumentHistoryRead = {
  document: DocumentRead;
  events: DocumentHistoryEventRead[];
};

type JournalEventRead = {
  id: string;
  occurred_at: string;
  actor: string;
  event_type: string;
  entity_type: string;
  entity_id: string;
  payload: Record<string, unknown>;
};

type ProgressEventRead = {
  id: string;
  job_id: string | null;
  occurred_at: string;
  event_type: string;
  message: string;
  payload: Record<string, unknown>;
};

type JobProgressGroup = {
  jobId: string;
  kind: string;
  status: string;
  eventCount: number;
  lastEventType: string;
  lastMessage: string;
  lastOccurredAt: string;
};

type AuditExportRead = {
  schema_version: string;
  generated_at: string;
  limit: number;
  journal_events: JournalEventRead[];
  progress_events: ProgressEventRead[];
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

async function loadAdminUsers(token: string): Promise<AdminUserRead[]> {
  return requestJson<AdminUserRead[]>("/admin/users", {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
}

async function loadAdminUserDomainGrants(
  token: string,
  adminUserId: string,
): Promise<AdminUserDomainGrantRead[]> {
  return requestJson<AdminUserDomainGrantRead[]>(`/admin/users/${adminUserId}/domain-grants`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
}

async function createAdminUser(
  token: string,
  payload: { email: string; password: string; roles: string[] },
): Promise<AdminUserRead> {
  return requestJson<AdminUserRead>("/admin/users", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
}

async function createAdminUserDomainGrant(
  token: string,
  adminUserId: string,
  domainId: string,
): Promise<AdminUserDomainGrantRead> {
  return requestJson<AdminUserDomainGrantRead>(`/admin/users/${adminUserId}/domain-grants`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ domain_id: domainId }),
  });
}

async function deleteAdminUserDomainGrant(
  token: string,
  adminUserId: string,
  domainId: string,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/admin/users/${adminUserId}/domain-grants/${domainId}`, {
    method: "DELETE",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  if (!response.ok) {
    throw new Error(`Request failed with ${response.status}`);
  }
}

async function updateAdminUserStatus(
  token: string,
  adminUserId: string,
  isActive: boolean,
): Promise<AdminUserRead> {
  return requestJson<AdminUserRead>(`/admin/users/${adminUserId}/status`, {
    method: "PATCH",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ is_active: isActive }),
  });
}

async function resetAdminUserPassword(
  token: string,
  adminUserId: string,
  password: string,
): Promise<AdminUserRead> {
  return requestJson<AdminUserRead>(`/admin/users/${adminUserId}/password`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ password }),
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

async function loadDocuments(
  token: string,
  domainId: string,
  includeArchived = false,
): Promise<DocumentRead[]> {
  const query = includeArchived ? "?include_archived=true" : "";
  return requestJson<DocumentRead[]>(`/domains/${domainId}/documents${query}`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
}

async function updateDocument(
  token: string,
  documentId: string,
  payload: { title: string },
): Promise<DocumentRead> {
  return requestJson<DocumentRead>(`/documents/${documentId}`, {
    method: "PATCH",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
}

async function archiveDocument(token: string, documentId: string): Promise<DocumentRead> {
  return requestJson<DocumentRead>(`/documents/${documentId}`, {
    method: "DELETE",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
}

async function restoreDocument(token: string, documentId: string): Promise<DocumentRead> {
  return requestJson<DocumentRead>(`/documents/${documentId}/restore`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
}

async function loadDocumentHistory(token: string, documentId: string): Promise<DocumentHistoryRead> {
  return requestJson<DocumentHistoryRead>(`/documents/${documentId}/history`, {
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

async function loadJob(token: string, jobId: string): Promise<JobRead> {
  return requestJson<JobRead>(`/jobs/${jobId}`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
}

async function retryJob(token: string, jobId: string): Promise<JobRead> {
  return requestJson<JobRead>(`/jobs/${jobId}/retry`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
}

async function loadJournalEvents(token: string): Promise<JournalEventRead[]> {
  return requestJson<JournalEventRead[]>("/audit/journal-events?limit=20", {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
}

async function loadAuditProgressEvents(token: string): Promise<ProgressEventRead[]> {
  return requestJson<ProgressEventRead[]>("/audit/progress-events?limit=20", {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
}

function auditExportFilename(disposition: string | null): string {
  const fallback = "retos-audit-export.json";
  if (!disposition) {
    return fallback;
  }
  const match = /filename="?([^";]+)"?/i.exec(disposition);
  return match?.[1] ?? fallback;
}

async function exportAuditSnapshot(
  token: string,
): Promise<{ filename: string; snapshot: AuditExportRead }> {
  const response = await fetch(`${API_BASE_URL}/audit/export?limit=200`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  if (!response.ok) {
    throw new Error(`Request failed with ${response.status}`);
  }
  const snapshot = (await response.json()) as AuditExportRead;
  const filename = auditExportFilename(response.headers.get("content-disposition"));
  const blob = new Blob([JSON.stringify(snapshot, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  return { filename, snapshot };
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

async function uploadDocumentFile(
  token: string,
  domainId: string,
  payload: {
    file: File;
    source_id: string | null;
    title: string | null;
  },
): Promise<JobRead> {
  const form = new FormData();
  form.append("file", payload.file);
  if (payload.source_id) {
    form.append("source_id", payload.source_id);
  }
  if (payload.title) {
    form.append("title", payload.title);
  }
  form.append("max_segment_tokens", "220");
  const response = await fetch(`${API_BASE_URL}/domains/${domainId}/ingestions/upload`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: form,
  });
  if (!response.ok) {
    throw new Error(`Request failed with ${response.status}`);
  }
  return (await response.json()) as JobRead;
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

async function runSmokeEval(token: string): Promise<EvalRunResponse> {
  return requestJson<EvalRunResponse>("/evals/smoke", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
}

async function runSquadEval(
  token: string,
  payload: {
    dataset_path: string;
    max_cases: number;
    write_report: boolean;
    report_stem: string | null;
  },
): Promise<EvalRunResponse> {
  return requestJson<EvalRunResponse>("/evals/squad", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
}

async function runHotpotQAEval(
  token: string,
  payload: {
    dataset_path: string;
    max_cases: number;
    write_report: boolean;
    report_stem: string | null;
  },
): Promise<EvalRunResponse> {
  return requestJson<EvalRunResponse>("/evals/hotpotqa", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
}

async function runNaturalQuestionsEval(
  token: string,
  payload: {
    dataset_path: string;
    max_cases: number;
    write_report: boolean;
    report_stem: string | null;
  },
): Promise<EvalRunResponse> {
  return requestJson<EvalRunResponse>("/evals/natural-questions", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
}

async function runOcrBenchmarkEval(
  token: string,
  payload: {
    dataset_path: string;
    dataset_format: string;
    max_cases: number;
    write_report: boolean;
    report_stem: string | null;
  },
): Promise<EvalRunResponse> {
  return requestJson<EvalRunResponse>("/evals/ocr-benchmark", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
}

async function loadEvalRuns(token: string): Promise<EvalRunRead[]> {
  return requestJson<EvalRunRead[]>("/evals/runs?limit=6", {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
}

async function loadEvalTrends(token: string): Promise<EvalSuiteTrend[]> {
  return requestJson<EvalSuiteTrend[]>("/evals/runs/trends?limit=60", {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
}

async function compareEvalRuns(
  token: string,
  baselineJobId: string,
  candidateJobId: string,
): Promise<EvalRunComparison> {
  const query = new URLSearchParams({
    baseline_job_id: baselineJobId,
    candidate_job_id: candidateJobId,
  });
  return requestJson<EvalRunComparison>(`/evals/runs/compare?${query.toString()}`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
}

async function rerunEval(token: string, jobId: string): Promise<EvalRunResponse> {
  return requestJson<EvalRunResponse>(`/evals/runs/${jobId}/rerun`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
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

function reportPathsFromPayload(payload: Record<string, unknown>): EvalReportPaths | null {
  const candidate = payload.report_paths;
  if (!candidate || typeof candidate !== "object") {
    return null;
  }
  const paths = candidate as Record<string, unknown>;
  if (typeof paths.json !== "string" || typeof paths.markdown !== "string") {
    return null;
  }
  return {
    json: paths.json,
    markdown: paths.markdown,
  };
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
    const parsed = JSON.parse(dataLines.join("\n")) as ProgressEvent;
    return { ...parsed, id: String(parsed.id) };
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

function eventStatus(event: ProgressEventRead): string | null {
  const status = event.payload.status;
  return typeof status === "string" && status.trim() ? status : null;
}

function groupProgressByJob(
  events: ProgressEventRead[],
  jobs: JobRead[],
): JobProgressGroup[] {
  const jobsById = new Map(jobs.map((job) => [job.id, job]));
  const groups = new Map<string, ProgressEventRead[]>();
  for (const event of events) {
    if (!event.job_id) {
      continue;
    }
    groups.set(event.job_id, [...(groups.get(event.job_id) ?? []), event]);
  }
  return [...groups.entries()]
    .map(([jobId, groupedEvents]) => {
      const sortedEvents = [...groupedEvents].sort((left, right) =>
        left.occurred_at.localeCompare(right.occurred_at),
      );
      const lastEvent = sortedEvents.at(-1) ?? sortedEvents[0];
      const job = jobsById.get(jobId);
      return {
        jobId,
        kind: job?.kind ?? "unknown",
        status: job?.status ?? eventStatus(lastEvent) ?? "unknown",
        eventCount: sortedEvents.length,
        lastEventType: lastEvent?.event_type ?? "unknown",
        lastMessage: lastEvent?.message ?? "No progress message",
        lastOccurredAt: lastEvent?.occurred_at ?? "",
      };
    })
    .sort((left, right) => right.lastOccurredAt.localeCompare(left.lastOccurredAt));
}

function formatHistoryValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "null";
  }
  const rendered = typeof value === "object" ? JSON.stringify(value) : String(value);
  return rendered.length > 160 ? `${rendered.slice(0, 157)}...` : rendered;
}

function evalMetadataEntries(report: EvalReport): [string, string][] {
  return Object.entries(report.metadata ?? {})
    .filter(([, value]) => value !== null && value !== undefined && value !== "")
    .map(([key, value]) => [key.replaceAll("_", " "), formatHistoryValue(value)]);
}

function formatScore(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function formatDelta(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatScore(value)}`;
}

function App() {
  const [email, setEmail] = useState("admin@retos.dev");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_STORAGE_KEY) ?? "");
  const [catalog, setCatalog] = useState<ProviderCatalog | null>(null);
  const [adminUsers, setAdminUsers] = useState<AdminUserRead[]>([]);
  const [adminUserEmail, setAdminUserEmail] = useState("");
  const [adminUserPassword, setAdminUserPassword] = useState("");
  const [adminUserRole, setAdminUserRole] = useState("admin");
  const [adminPasswordResets, setAdminPasswordResets] = useState<Record<string, string>>({});
  const [adminDomainGrants, setAdminDomainGrants] = useState<
    Record<string, AdminUserDomainGrantRead[]>
  >({});
  const [adminGrantDomainIds, setAdminGrantDomainIds] = useState<Record<string, string>>({});
  const [isCreatingAdminUser, setIsCreatingAdminUser] = useState(false);
  const [savingAdminUserId, setSavingAdminUserId] = useState<string | null>(null);
  const [adminUserError, setAdminUserError] = useState<string | null>(null);
  const [adminUserMessage, setAdminUserMessage] = useState<string | null>(null);
  const [isLoadingProvider, setIsLoadingProvider] = useState(false);
  const [providerError, setProviderError] = useState<string | null>(null);
  const [domains, setDomains] = useState<DomainRead[]>([]);
  const [selectedDomainId, setSelectedDomainId] = useState("");
  const [documents, setDocuments] = useState<DocumentRead[]>([]);
  const [sources, setSources] = useState<SourceRead[]>([]);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [isLoadingWorkspace, setIsLoadingWorkspace] = useState(false);
  const [editingDocumentId, setEditingDocumentId] = useState<string | null>(null);
  const [documentEditTitle, setDocumentEditTitle] = useState("");
  const [isUpdatingDocument, setIsUpdatingDocument] = useState(false);
  const [archivingDocumentId, setArchivingDocumentId] = useState<string | null>(null);
  const [restoringDocumentId, setRestoringDocumentId] = useState<string | null>(null);
  const [showArchivedDocuments, setShowArchivedDocuments] = useState(false);
  const [historyDocumentId, setHistoryDocumentId] = useState<string | null>(null);
  const [documentHistory, setDocumentHistory] = useState<DocumentHistoryRead | null>(null);
  const [isLoadingDocumentHistory, setIsLoadingDocumentHistory] = useState(false);
  const [isCreatingDomain, setIsCreatingDomain] = useState(false);
  const [isCreatingSource, setIsCreatingSource] = useState(false);
  const [sourceName, setSourceName] = useState("");
  const [sourceUri, setSourceUri] = useState("");
  const [sourceKind, setSourceKind] = useState<SourceKind>("mount");
  const [isQueueingScan, setIsQueueingScan] = useState(false);
  const [isQueueingIndex, setIsQueueingIndex] = useState(false);
  const [queuedJobs, setQueuedJobs] = useState<JobRead[]>([]);
  const [isIngestingText, setIsIngestingText] = useState(false);
  const [isUploadingFile, setIsUploadingFile] = useState(false);
  const [textTitle, setTextTitle] = useState("");
  const [textBody, setTextBody] = useState("");
  const [textSourceId, setTextSourceId] = useState("");
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploadSourceId, setUploadSourceId] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [domainSlug, setDomainSlug] = useState("");
  const [domainName, setDomainName] = useState("");
  const [domainDescription, setDomainDescription] = useState("");
  const [question, setQuestion] = useState("");
  const [queryResult, setQueryResult] = useState<AgentQueryResult | null>(null);
  const [queryJob, setQueryJob] = useState<JobRead | null>(null);
  const [isRunningQuery, setIsRunningQuery] = useState(false);
  const [queryError, setQueryError] = useState<string | null>(null);
  const [evalReport, setEvalReport] = useState<EvalReport | null>(null);
  const [evalJob, setEvalJob] = useState<JobRead | null>(null);
  const [evalReportPaths, setEvalReportPaths] = useState<EvalReportPaths | null>(null);
  const [evalRuns, setEvalRuns] = useState<EvalRunRead[]>([]);
  const [evalTrends, setEvalTrends] = useState<EvalSuiteTrend[]>([]);
  const [evalComparison, setEvalComparison] = useState<EvalRunComparison | null>(null);
  const [isRunningEval, setIsRunningEval] = useState(false);
  const [isRunningSquadEval, setIsRunningSquadEval] = useState(false);
  const [isRunningHotpotQAEval, setIsRunningHotpotQAEval] = useState(false);
  const [isRunningNaturalQuestionsEval, setIsRunningNaturalQuestionsEval] = useState(false);
  const [isRunningOcrBenchmarkEval, setIsRunningOcrBenchmarkEval] = useState(false);
  const [isComparingEvals, setIsComparingEvals] = useState(false);
  const [rerunningEvalJobId, setRerunningEvalJobId] = useState<string | null>(null);
  const [squadDatasetPath, setSquadDatasetPath] = useState("dev-v2.0.json");
  const [squadMaxCases, setSquadMaxCases] = useState("50");
  const [squadWriteReport, setSquadWriteReport] = useState(true);
  const [squadReportStem, setSquadReportStem] = useState("squad-v2-dev-50");
  const [hotpotqaDatasetPath, setHotpotqaDatasetPath] = useState(
    "hotpot_dev_distractor_v1.json",
  );
  const [hotpotqaMaxCases, setHotpotqaMaxCases] = useState("50");
  const [hotpotqaWriteReport, setHotpotqaWriteReport] = useState(true);
  const [hotpotqaReportStem, setHotpotqaReportStem] = useState("hotpotqa-dev-50");
  const [naturalQuestionsDatasetPath, setNaturalQuestionsDatasetPath] = useState(
    "nq-dev-sample.jsonl",
  );
  const [naturalQuestionsMaxCases, setNaturalQuestionsMaxCases] = useState("50");
  const [naturalQuestionsWriteReport, setNaturalQuestionsWriteReport] = useState(true);
  const [naturalQuestionsReportStem, setNaturalQuestionsReportStem] = useState(
    "natural-questions-dev-50",
  );
  const [ocrBenchmarkDatasetPath, setOcrBenchmarkDatasetPath] =
    useState("ocr-benchmark/manifest.json");
  const [ocrBenchmarkFormat, setOcrBenchmarkFormat] = useState("manifest");
  const [ocrBenchmarkMaxCases, setOcrBenchmarkMaxCases] = useState("25");
  const [ocrBenchmarkWriteReport, setOcrBenchmarkWriteReport] = useState(true);
  const [ocrBenchmarkReportStem, setOcrBenchmarkReportStem] = useState("ocr-benchmark-25");
  const [evalError, setEvalError] = useState<string | null>(null);
  const [liveStatus, setLiveStatus] = useState<LiveStatus>("disconnected");
  const [liveError, setLiveError] = useState<string | null>(null);
  const [progressEvents, setProgressEvents] = useState<ProgressEvent[]>([]);
  const [lastProgressCursor, setLastProgressCursor] = useState<string | null>(null);
  const [jobFilter, setJobFilter] = useState("all");
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [selectedJob, setSelectedJob] = useState<JobRead | null>(null);
  const [isLoadingJobDetail, setIsLoadingJobDetail] = useState(false);
  const [retryingJobId, setRetryingJobId] = useState<string | null>(null);
  const [jobDetailError, setJobDetailError] = useState<string | null>(null);
  const [journalEvents, setJournalEvents] = useState<JournalEventRead[]>([]);
  const [auditProgressEvents, setAuditProgressEvents] = useState<ProgressEventRead[]>([]);
  const [isLoadingAudit, setIsLoadingAudit] = useState(false);
  const [isExportingAudit, setIsExportingAudit] = useState(false);
  const [auditError, setAuditError] = useState<string | null>(null);
  const [auditExportMessage, setAuditExportMessage] = useState<string | null>(null);
  const liveAbortRef = useRef<AbortController | null>(null);
  const lastPersistedEventIdRef = useRef<string | null>(null);

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

  const domainById = useMemo(
    () => new Map(domains.map((domain) => [domain.id, domain])),
    [domains],
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
  const progressGroups = useMemo(
    () => groupProgressByJob(auditProgressEvents, queuedJobs),
    [auditProgressEvents, queuedJobs],
  );
  const selectedJobProgressEvents = useMemo(
    () =>
      selectedJobId
        ? auditProgressEvents.filter((event) => event.job_id === selectedJobId)
        : [],
    [auditProgressEvents, selectedJobId],
  );
  const isAnyEvalRunning =
    isRunningEval ||
    isRunningSquadEval ||
    isRunningHotpotQAEval ||
    isRunningNaturalQuestionsEval ||
    isRunningOcrBenchmarkEval ||
    rerunningEvalJobId !== null;
  const comparableEvalRuns = evalRuns.filter((run) => run.report !== null);

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
          loadDocuments(adminToken, nextSelectedDomainId, showArchivedDocuments),
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

  async function refreshAudit(accessToken?: string) {
    setIsLoadingAudit(true);
    setAuditError(null);
    setAuditExportMessage(null);
    try {
      const adminToken = accessToken ?? (await getAdminToken());
      const [nextJournalEvents, nextProgressEvents, nextJobs] = await Promise.all([
        loadJournalEvents(adminToken),
        loadAuditProgressEvents(adminToken),
        loadJobs(adminToken),
      ]);
      setJournalEvents(nextJournalEvents);
      setAuditProgressEvents(nextProgressEvents);
      setQueuedJobs(nextJobs);
    } catch (error) {
      setAuditError(error instanceof Error ? error.message : "Audit refresh failed");
    } finally {
      setIsLoadingAudit(false);
    }
  }

  async function handleInspectJob(jobId: string) {
    setSelectedJobId(jobId);
    setJobDetailError(null);
    setIsLoadingJobDetail(true);
    try {
      const accessToken = await getAdminToken();
      const [job] = await Promise.all([loadJob(accessToken, jobId), refreshAudit(accessToken)]);
      setSelectedJob(job);
      setQueuedJobs((current) =>
        [job, ...current.filter((candidate) => candidate.id !== job.id)].slice(0, 12),
      );
    } catch (error) {
      setJobDetailError(error instanceof Error ? error.message : "Job detail failed to load");
    } finally {
      setIsLoadingJobDetail(false);
    }
  }

  function handleCloseJobDetail() {
    setSelectedJobId(null);
    setSelectedJob(null);
    setJobDetailError(null);
  }

  async function handleRetryJob(jobId: string) {
    setRetryingJobId(jobId);
    setAuditError(null);
    try {
      const accessToken = await getAdminToken();
      const retried = await retryJob(accessToken, jobId);
      setQueuedJobs((current) =>
        [retried, ...current.filter((candidate) => candidate.id !== retried.id)].slice(0, 12),
      );
      setSelectedJobId(retried.id);
      setSelectedJob(retried);
      await refreshAudit(accessToken);
    } catch (error) {
      setAuditError(error instanceof Error ? error.message : "Job retry failed");
    } finally {
      setRetryingJobId(null);
    }
  }

  async function handleExportAudit() {
    setIsExportingAudit(true);
    setAuditError(null);
    setAuditExportMessage(null);
    try {
      const accessToken = await getAdminToken();
      const { filename, snapshot } = await exportAuditSnapshot(accessToken);
      setAuditExportMessage(
        `${filename}: ${snapshot.journal_events.length} journal, ${snapshot.progress_events.length} progress`,
      );
    } catch (error) {
      setAuditError(error instanceof Error ? error.message : "Audit export failed");
    } finally {
      setIsExportingAudit(false);
    }
  }

  async function refreshEvalRuns(accessToken?: string) {
    setEvalError(null);
    try {
      const adminToken = accessToken ?? (await getAdminToken());
      const [runs, trends] = await Promise.all([
        loadEvalRuns(adminToken),
        loadEvalTrends(adminToken),
      ]);
      setEvalRuns(runs);
      setEvalTrends(trends);
      const latestWithReport = runs.find((run) => run.report !== null);
      setEvalJob(runs[0]?.job ?? null);
      setEvalReport(latestWithReport?.report ?? null);
      setEvalReportPaths(
        latestWithReport ? reportPathsFromPayload(latestWithReport.job.payload) : null,
      );
      setEvalComparison(null);
    } catch (error) {
      setEvalError(error instanceof Error ? error.message : "Eval history refresh failed");
    }
  }

  async function refreshAdminUsers(accessToken?: string) {
    setAdminUserError(null);
    try {
      const adminToken = accessToken ?? (await getAdminToken());
      const users = await loadAdminUsers(adminToken);
      setAdminUsers(users);
      const grantsByUser = await Promise.all(
        users.map(async (user) => [user.id, await loadAdminUserDomainGrants(adminToken, user.id)] as const),
      );
      setAdminDomainGrants(Object.fromEntries(grantsByUser));
    } catch (error) {
      setAdminUserError(error instanceof Error ? error.message : "Admin users refresh failed");
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
      await refreshAdminUsers(accessToken);
      await refreshWorkspace(accessToken);
      await refreshAudit(accessToken);
      await refreshEvalRuns(accessToken);
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

  async function handleCreateAdminUser(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsCreatingAdminUser(true);
    setAdminUserError(null);
    setAdminUserMessage(null);
    try {
      const nextEmail = adminUserEmail.trim();
      if (!nextEmail) {
        throw new Error("Admin email is required");
      }
      if (adminUserPassword.length < 12) {
        throw new Error("Admin password must be at least 12 characters");
      }
      const accessToken = await getAdminToken();
      const created = await createAdminUser(accessToken, {
        email: nextEmail,
        password: adminUserPassword,
        roles: [adminUserRole],
      });
      setAdminUsers((current) => [...current.filter((user) => user.id !== created.id), created]);
      setAdminUserEmail("");
      setAdminUserPassword("");
      setAdminUserRole("admin");
      setAdminUserMessage(`Created ${created.email}`);
      await refreshAudit(accessToken);
    } catch (error) {
      setAdminUserError(error instanceof Error ? error.message : "Admin user create failed");
    } finally {
      setIsCreatingAdminUser(false);
    }
  }

  async function handleUpdateAdminUserStatus(user: AdminUserRead) {
    setSavingAdminUserId(user.id);
    setAdminUserError(null);
    setAdminUserMessage(null);
    try {
      const accessToken = await getAdminToken();
      const updated = await updateAdminUserStatus(accessToken, user.id, !user.is_active);
      setAdminUsers((current) =>
        current.map((candidate) => (candidate.id === updated.id ? updated : candidate)),
      );
      setAdminUserMessage(`${updated.email} is now ${updated.is_active ? "active" : "inactive"}`);
      await refreshAudit(accessToken);
    } catch (error) {
      setAdminUserError(error instanceof Error ? error.message : "Admin status update failed");
    } finally {
      setSavingAdminUserId(null);
    }
  }

  async function handleResetAdminPassword(
    event: React.FormEvent<HTMLFormElement>,
    user: AdminUserRead,
  ) {
    event.preventDefault();
    setSavingAdminUserId(user.id);
    setAdminUserError(null);
    setAdminUserMessage(null);
    try {
      const nextPassword = adminPasswordResets[user.id] ?? "";
      if (nextPassword.length < 12) {
        throw new Error("Admin password must be at least 12 characters");
      }
      const accessToken = await getAdminToken();
      const updated = await resetAdminUserPassword(accessToken, user.id, nextPassword);
      setAdminUsers((current) =>
        current.map((candidate) => (candidate.id === updated.id ? updated : candidate)),
      );
      setAdminPasswordResets((current) => ({ ...current, [user.id]: "" }));
      setAdminUserMessage(`Updated password for ${updated.email}`);
      await refreshAudit(accessToken);
    } catch (error) {
      setAdminUserError(error instanceof Error ? error.message : "Admin password reset failed");
    } finally {
      setSavingAdminUserId(null);
    }
  }

  async function handleCreateDomainGrant(
    event: React.FormEvent<HTMLFormElement>,
    user: AdminUserRead,
  ) {
    event.preventDefault();
    setSavingAdminUserId(user.id);
    setAdminUserError(null);
    setAdminUserMessage(null);
    try {
      const domainId = adminGrantDomainIds[user.id] ?? "";
      if (!domainId) {
        throw new Error("Select a domain grant");
      }
      const accessToken = await getAdminToken();
      const grant = await createAdminUserDomainGrant(accessToken, user.id, domainId);
      setAdminDomainGrants((current) => ({
        ...current,
        [user.id]: [...(current[user.id] ?? []).filter((item) => item.domain_id !== domainId), grant],
      }));
      setAdminGrantDomainIds((current) => ({ ...current, [user.id]: "" }));
      setAdminUserMessage(`Granted ${user.email} access to ${domainById.get(domainId)?.slug ?? domainId}`);
      await refreshAudit(accessToken);
    } catch (error) {
      setAdminUserError(error instanceof Error ? error.message : "Domain grant failed");
    } finally {
      setSavingAdminUserId(null);
    }
  }

  async function handleDeleteDomainGrant(user: AdminUserRead, domainId: string) {
    setSavingAdminUserId(user.id);
    setAdminUserError(null);
    setAdminUserMessage(null);
    try {
      const accessToken = await getAdminToken();
      await deleteAdminUserDomainGrant(accessToken, user.id, domainId);
      setAdminDomainGrants((current) => ({
        ...current,
        [user.id]: (current[user.id] ?? []).filter((grant) => grant.domain_id !== domainId),
      }));
      setAdminUserMessage(`Revoked ${user.email} access to ${domainById.get(domainId)?.slug ?? domainId}`);
      await refreshAudit(accessToken);
    } catch (error) {
      setAdminUserError(error instanceof Error ? error.message : "Domain revoke failed");
    } finally {
      setSavingAdminUserId(null);
    }
  }

  async function handleDomainChange(nextDomainId: string) {
    setSelectedDomainId(nextDomainId);
    setQueryResult(null);
    setQueryJob(null);
    setWorkspaceError(null);
    setTextSourceId("");
    handleCancelDocumentEdit();
    clearDocumentHistory();
    if (!nextDomainId) {
      setDocuments([]);
      setSources([]);
      return;
    }
    setIsLoadingWorkspace(true);
    try {
      const accessToken = await getAdminToken();
      const [nextDocuments, nextSources, nextJobs] = await Promise.all([
        loadDocuments(accessToken, nextDomainId, showArchivedDocuments),
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

  function handleStartDocumentEdit(document: DocumentRead) {
    setEditingDocumentId(document.id);
    setDocumentEditTitle(document.title);
    setWorkspaceError(null);
  }

  function handleCancelDocumentEdit() {
    setEditingDocumentId(null);
    setDocumentEditTitle("");
  }

  function clearDocumentHistory() {
    setHistoryDocumentId(null);
    setDocumentHistory(null);
  }

  async function handleUpdateDocument(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError(null);
    setIsUpdatingDocument(true);
    try {
      if (!editingDocumentId) {
        throw new Error("Choose a document before updating it");
      }
      const title = documentEditTitle.trim();
      if (!title) {
        throw new Error("Document title is required");
      }
      const accessToken = await getAdminToken();
      const updated = await updateDocument(accessToken, editingDocumentId, { title });
      setDocuments((current) =>
        current.map((document) => (document.id === updated.id ? updated : document)),
      );
      setEditingDocumentId(null);
      setDocumentEditTitle("");
      if (historyDocumentId === updated.id) {
        setDocumentHistory(await loadDocumentHistory(accessToken, updated.id));
      }
      await refreshAudit(accessToken);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Document update failed");
    } finally {
      setIsUpdatingDocument(false);
    }
  }

  async function handleArchiveDocument(documentId: string) {
    setWorkspaceError(null);
    setArchivingDocumentId(documentId);
    try {
      const accessToken = await getAdminToken();
      const archived = await archiveDocument(accessToken, documentId);
      setDocuments((current) =>
        showArchivedDocuments
          ? current.map((document) => (document.id === archived.id ? archived : document))
          : current.filter((document) => document.id !== archived.id),
      );
      if (editingDocumentId === documentId) {
        handleCancelDocumentEdit();
      }
      if (historyDocumentId === archived.id) {
        setDocumentHistory(await loadDocumentHistory(accessToken, archived.id));
      }
      await refreshAudit(accessToken);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Document archive failed");
    } finally {
      setArchivingDocumentId(null);
    }
  }

  async function handleRestoreDocument(documentId: string) {
    setWorkspaceError(null);
    setRestoringDocumentId(documentId);
    try {
      const accessToken = await getAdminToken();
      const restored = await restoreDocument(accessToken, documentId);
      setDocuments((current) =>
        current.map((document) => (document.id === restored.id ? restored : document)),
      );
      if (historyDocumentId === restored.id) {
        setDocumentHistory(await loadDocumentHistory(accessToken, restored.id));
      }
      await refreshAudit(accessToken);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Document restore failed");
    } finally {
      setRestoringDocumentId(null);
    }
  }

  async function handleArchivedToggle(event: React.ChangeEvent<HTMLInputElement>) {
    const nextShowArchived = event.target.checked;
    setShowArchivedDocuments(nextShowArchived);
    handleCancelDocumentEdit();
    setWorkspaceError(null);
    if (!selectedDomainId) {
      return;
    }
    setIsLoadingWorkspace(true);
    try {
      const accessToken = await getAdminToken();
      const [nextDocuments, nextJobs] = await Promise.all([
        loadDocuments(accessToken, selectedDomainId, nextShowArchived),
        loadJobs(accessToken),
      ]);
      setDocuments(nextDocuments);
      setQueuedJobs(nextJobs);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Document refresh failed");
    } finally {
      setIsLoadingWorkspace(false);
    }
  }

  async function handleDocumentHistory(documentId: string) {
    if (historyDocumentId === documentId) {
      clearDocumentHistory();
      return;
    }
    setWorkspaceError(null);
    setHistoryDocumentId(documentId);
    setDocumentHistory(null);
    setIsLoadingDocumentHistory(true);
    try {
      const accessToken = await getAdminToken();
      setDocumentHistory(await loadDocumentHistory(accessToken, documentId));
    } catch (error) {
      clearDocumentHistory();
      setWorkspaceError(error instanceof Error ? error.message : "Document history failed");
    } finally {
      setIsLoadingDocumentHistory(false);
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
        loadDocuments(accessToken, selectedDomainId, showArchivedDocuments),
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

  async function handleUploadFile(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const uploadForm = event.currentTarget;
    setWorkspaceError(null);
    setIsUploadingFile(true);
    try {
      if (!selectedDomainId) {
        throw new Error("Select a domain before uploading a file");
      }
      if (!uploadFile) {
        throw new Error("Choose a supported .txt, .md, or .pdf file");
      }
      const accessToken = await getAdminToken();
      const job = await uploadDocumentFile(accessToken, selectedDomainId, {
        file: uploadFile,
        source_id: uploadSourceId || null,
        title: uploadTitle.trim() || null,
      });
      setQueuedJobs((current) => [job, ...current].slice(0, 6));
      setUploadTitle("");
      setUploadSourceId("");
      setUploadFile(null);
      const uploadInput = uploadForm.elements.namedItem("uploadFile");
      if (uploadInput instanceof HTMLInputElement) {
        uploadInput.value = "";
      }
      const [nextDocuments, nextJobs] = await Promise.all([
        loadDocuments(accessToken, selectedDomainId, showArchivedDocuments),
        loadJobs(accessToken),
      ]);
      setDocuments(nextDocuments);
      setQueuedJobs(nextJobs.length > 0 ? nextJobs : [job]);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "File upload failed");
    } finally {
      setIsUploadingFile(false);
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

  async function handleRunSmokeEval() {
    setIsRunningEval(true);
    setEvalError(null);
    try {
      const accessToken = await getAdminToken();
      const response = await runSmokeEval(accessToken);
      applyEvalResponse(response);
      await refreshAudit(accessToken);
      await refreshEvalRuns(accessToken);
    } catch (error) {
      setEvalError(error instanceof Error ? error.message : "Eval smoke failed");
    } finally {
      setIsRunningEval(false);
    }
  }

  async function handleRunSquadEval(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsRunningSquadEval(true);
    setEvalError(null);
    try {
      const datasetPath = squadDatasetPath.trim();
      const parsedMaxCases = Number.parseInt(squadMaxCases, 10);
      if (!datasetPath) {
        throw new Error("SQuAD dataset path is required");
      }
      if (!Number.isInteger(parsedMaxCases) || parsedMaxCases < 1 || parsedMaxCases > 1000) {
        throw new Error("SQuAD max cases must be between 1 and 1000");
      }
      const accessToken = await getAdminToken();
      const response = await runSquadEval(accessToken, {
        dataset_path: datasetPath,
        max_cases: parsedMaxCases,
        write_report: squadWriteReport,
        report_stem: squadReportStem.trim() || null,
      });
      applyEvalResponse(response);
      await refreshAudit(accessToken);
      await refreshEvalRuns(accessToken);
    } catch (error) {
      setEvalError(error instanceof Error ? error.message : "SQuAD eval failed");
    } finally {
      setIsRunningSquadEval(false);
    }
  }

  async function handleRunHotpotQAEval(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsRunningHotpotQAEval(true);
    setEvalError(null);
    try {
      const datasetPath = hotpotqaDatasetPath.trim();
      const parsedMaxCases = Number.parseInt(hotpotqaMaxCases, 10);
      if (!datasetPath) {
        throw new Error("HotpotQA dataset path is required");
      }
      if (!Number.isInteger(parsedMaxCases) || parsedMaxCases < 1 || parsedMaxCases > 1000) {
        throw new Error("HotpotQA max cases must be between 1 and 1000");
      }
      const accessToken = await getAdminToken();
      const response = await runHotpotQAEval(accessToken, {
        dataset_path: datasetPath,
        max_cases: parsedMaxCases,
        write_report: hotpotqaWriteReport,
        report_stem: hotpotqaReportStem.trim() || null,
      });
      applyEvalResponse(response);
      await refreshAudit(accessToken);
      await refreshEvalRuns(accessToken);
    } catch (error) {
      setEvalError(error instanceof Error ? error.message : "HotpotQA eval failed");
    } finally {
      setIsRunningHotpotQAEval(false);
    }
  }

  async function handleRunNaturalQuestionsEval(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsRunningNaturalQuestionsEval(true);
    setEvalError(null);
    try {
      const datasetPath = naturalQuestionsDatasetPath.trim();
      const parsedMaxCases = Number.parseInt(naturalQuestionsMaxCases, 10);
      if (!datasetPath) {
        throw new Error("Natural Questions dataset path is required");
      }
      if (!Number.isInteger(parsedMaxCases) || parsedMaxCases < 1 || parsedMaxCases > 1000) {
        throw new Error("Natural Questions max cases must be between 1 and 1000");
      }
      const accessToken = await getAdminToken();
      const response = await runNaturalQuestionsEval(accessToken, {
        dataset_path: datasetPath,
        max_cases: parsedMaxCases,
        write_report: naturalQuestionsWriteReport,
        report_stem: naturalQuestionsReportStem.trim() || null,
      });
      applyEvalResponse(response);
      await refreshAudit(accessToken);
      await refreshEvalRuns(accessToken);
    } catch (error) {
      setEvalError(error instanceof Error ? error.message : "Natural Questions eval failed");
    } finally {
      setIsRunningNaturalQuestionsEval(false);
    }
  }

  async function handleRunOcrBenchmarkEval(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsRunningOcrBenchmarkEval(true);
    setEvalError(null);
    try {
      const datasetPath = ocrBenchmarkDatasetPath.trim();
      const parsedMaxCases = Number.parseInt(ocrBenchmarkMaxCases, 10);
      if (!datasetPath) {
        throw new Error("OCR benchmark dataset path is required");
      }
      if (!Number.isInteger(parsedMaxCases) || parsedMaxCases < 1 || parsedMaxCases > 1000) {
        throw new Error("OCR benchmark max cases must be between 1 and 1000");
      }
      const accessToken = await getAdminToken();
      const response = await runOcrBenchmarkEval(accessToken, {
        dataset_path: datasetPath,
        dataset_format: ocrBenchmarkFormat,
        max_cases: parsedMaxCases,
        write_report: ocrBenchmarkWriteReport,
        report_stem: ocrBenchmarkReportStem.trim() || null,
      });
      applyEvalResponse(response);
      await refreshAudit(accessToken);
      await refreshEvalRuns(accessToken);
    } catch (error) {
      setEvalError(error instanceof Error ? error.message : "OCR benchmark eval failed");
    } finally {
      setIsRunningOcrBenchmarkEval(false);
    }
  }

  async function handleCompareLatestEvals() {
    setIsComparingEvals(true);
    setEvalError(null);
    try {
      const [candidate, baseline] = comparableEvalRuns;
      if (!candidate || !baseline) {
        throw new Error("At least two reported eval runs are required for comparison");
      }
      const accessToken = await getAdminToken();
      const comparison = await compareEvalRuns(accessToken, baseline.job.id, candidate.job.id);
      setEvalComparison(comparison);
    } catch (error) {
      setEvalError(error instanceof Error ? error.message : "Eval comparison failed");
    } finally {
      setIsComparingEvals(false);
    }
  }

  async function handleRerunEval(jobId: string) {
    setRerunningEvalJobId(jobId);
    setEvalError(null);
    try {
      const accessToken = await getAdminToken();
      const response = await rerunEval(accessToken, jobId);
      applyEvalResponse(response);
      await refreshAudit(accessToken);
      await refreshEvalRuns(accessToken);
    } catch (error) {
      setEvalError(error instanceof Error ? error.message : "Eval rerun failed");
    } finally {
      setRerunningEvalJobId(null);
    }
  }

  function applyEvalResponse(response: EvalRunResponse) {
    setEvalJob(response.job);
    setEvalReport(response.report);
    setEvalReportPaths(response.report_paths ?? reportPathsFromPayload(response.job.payload));
    setEvalComparison(null);
    setEvalRuns((current) =>
      [
        { job: response.job, report: response.report },
        ...current.filter((run) => run.job.id !== response.job.id),
      ].slice(0, 6),
    );
    setQueuedJobs((current) =>
      [response.job, ...current.filter((job) => job.id !== response.job.id)].slice(0, 12),
    );
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
      const liveHeaders: HeadersInit = {
        Authorization: `Bearer ${accessToken}`,
      };
      if (lastPersistedEventIdRef.current) {
        liveHeaders["Last-Event-ID"] = lastPersistedEventIdRef.current;
      }
      const response = await fetch(`${API_BASE_URL}/events/progress`, {
        headers: liveHeaders,
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
          const lastPersisted = nextEvents.findLast((event) =>
            event.id.startsWith("progress:"),
          );
          if (lastPersisted) {
            lastPersistedEventIdRef.current = lastPersisted.id;
            setLastProgressCursor(lastPersisted.id);
          }
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
    setAdminUsers([]);
    setAdminUserEmail("");
    setAdminUserPassword("");
    setAdminUserRole("admin");
    setAdminPasswordResets({});
    setAdminDomainGrants({});
    setAdminGrantDomainIds({});
    setAdminUserError(null);
    setAdminUserMessage(null);
    setSavingAdminUserId(null);
    setProviderError(null);
    setQueryResult(null);
    setQueryJob(null);
    setEvalReport(null);
    setEvalJob(null);
    setEvalReportPaths(null);
    setEvalRuns([]);
    setEvalTrends([]);
    setEvalComparison(null);
    setEvalError(null);
    setDomains([]);
    setSelectedDomainId("");
    setDocuments([]);
    setEditingDocumentId(null);
    setDocumentEditTitle("");
    setArchivingDocumentId(null);
    setRestoringDocumentId(null);
    setShowArchivedDocuments(false);
    clearDocumentHistory();
    setSources([]);
    setWorkspaceError(null);
    setLiveStatus("disconnected");
    setLiveError(null);
    setProgressEvents([]);
    setLastProgressCursor(null);
    lastPersistedEventIdRef.current = null;
    setQueuedJobs([]);
    setJournalEvents([]);
    setAuditProgressEvents([]);
    setAuditError(null);
    setTextTitle("");
    setTextBody("");
    setTextSourceId("");
    setUploadTitle("");
    setUploadSourceId("");
    setUploadFile(null);
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
          <a href="#evals">Evals</a>
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
              <label className="toggle-control">
                <input
                  type="checkbox"
                  checked={showArchivedDocuments}
                  disabled={!selectedDomainId || isLoadingWorkspace}
                  onChange={(event) => void handleArchivedToggle(event)}
                />
                <span>Show archived</span>
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
              {documents.map((document) => {
                const isEditing = editingDocumentId === document.id;
                const isArchived = document.archived_at !== null;
                const isArchiving = archivingDocumentId === document.id;
                const isRestoring = restoringDocumentId === document.id;
                const isHistoryOpen = historyDocumentId === document.id;
                return (
                  <article className={`document-row${isArchived ? " archived" : ""}`} key={document.id}>
                    <div className="document-summary">
                      {isEditing ? (
                        <form className="document-edit-form" onSubmit={handleUpdateDocument}>
                          <label>
                            <span>Document title</span>
                            <input
                              aria-label={`Document title for ${document.title}`}
                              value={documentEditTitle}
                              onChange={(event) => setDocumentEditTitle(event.target.value)}
                            />
                          </label>
                          <div className="document-actions">
                            <button
                              className="icon-button"
                              disabled={isUpdatingDocument}
                              title="Save document title"
                              type="submit"
                              aria-label={`Save ${document.title}`}
                            >
                              <Check aria-hidden="true" />
                            </button>
                            <button
                              className="icon-button"
                              disabled={isUpdatingDocument}
                              title="Cancel document edit"
                              type="button"
                              aria-label={`Cancel editing ${document.title}`}
                              onClick={handleCancelDocumentEdit}
                            >
                              <X aria-hidden="true" />
                            </button>
                          </div>
                        </form>
                      ) : (
                        <>
                          <strong>{document.title}</strong>
                          <span>{document.source_uri ?? document.external_id ?? document.id}</span>
                        </>
                      )}
                    </div>
                    <div className="document-meta">
                      <span className="badge muted">{document.content_hash.slice(0, 10)}</span>
                      {isArchived ? <span className="badge warning">Archived</span> : null}
                      <div className="document-actions">
                        <button
                          className="icon-button"
                          disabled={isEditing || isArchiving || isRestoring || isArchived}
                          title="Edit document title"
                          type="button"
                          aria-label={`Edit ${document.title}`}
                          onClick={() => handleStartDocumentEdit(document)}
                        >
                          <Pencil aria-hidden="true" />
                        </button>
                        <button
                          className="icon-button"
                          disabled={isEditing || isLoadingDocumentHistory}
                          title="View document history"
                          type="button"
                          aria-label={`History ${document.title}`}
                          onClick={() => void handleDocumentHistory(document.id)}
                        >
                          {isHistoryOpen && isLoadingDocumentHistory ? (
                            <RefreshCw aria-hidden="true" />
                          ) : (
                            <History aria-hidden="true" />
                          )}
                        </button>
                        {isArchived ? (
                          <button
                            className="icon-button"
                            disabled={isEditing || isRestoring}
                            title="Restore document"
                            type="button"
                            aria-label={`Restore ${document.title}`}
                            onClick={() => void handleRestoreDocument(document.id)}
                          >
                            {isRestoring ? <RefreshCw aria-hidden="true" /> : <RotateCcw aria-hidden="true" />}
                          </button>
                        ) : (
                          <button
                            className="icon-button danger"
                            disabled={isEditing || isArchiving}
                            title="Archive document"
                            type="button"
                            aria-label={`Archive ${document.title}`}
                            onClick={() => void handleArchiveDocument(document.id)}
                          >
                            {isArchiving ? <RefreshCw aria-hidden="true" /> : <Archive aria-hidden="true" />}
                          </button>
                        )}
                      </div>
                    </div>
                    {isHistoryOpen ? (
                      <section className="document-history" aria-label={`History for ${document.title}`}>
                        {!documentHistory || isLoadingDocumentHistory ? (
                          <p className="payload-summary">Loading document history</p>
                        ) : documentHistory.events.length > 0 ? (
                          documentHistory.events.map((event) => (
                            <article className="history-event" key={event.id}>
                              <div>
                                <strong>{event.event_type}</strong>
                                <span>
                                  {formatDateTime(event.occurred_at)} by {event.actor}
                                </span>
                              </div>
                              {event.changes.length > 0 ? (
                                <div className="history-changes">
                                  {event.changes.map((change) => (
                                    <div className="history-change" key={`${event.id}-${change.field}`}>
                                      <span>{change.field}</span>
                                      <code>{formatHistoryValue(change.before)}</code>
                                      <code>{formatHistoryValue(change.after)}</code>
                                    </div>
                                  ))}
                                </div>
                              ) : (
                                <p className="payload-summary">{summarizePayload(event.payload)}</p>
                              )}
                            </article>
                          ))
                        ) : (
                          <p className="payload-summary">No document journal events recorded.</p>
                        )}
                      </section>
                    ) : null}
                  </article>
                );
              })}
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
            <section className="file-upload" aria-label="File upload">
              <div className="section-heading">
                <h3>File upload</h3>
              </div>
              <form className="file-upload-form" onSubmit={handleUploadFile}>
                <label>
                  <span>File</span>
                  <input
                    aria-label="Upload file"
                    accept=".txt,.md,.pdf,text/plain,text/markdown,application/pdf"
                    name="uploadFile"
                    type="file"
                    onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
                  />
                </label>
                <label>
                  <span>Title</span>
                  <input
                    placeholder="Uploaded research note"
                    value={uploadTitle}
                    onChange={(event) => setUploadTitle(event.target.value)}
                  />
                </label>
                <label className="span-two">
                  <span>Source</span>
                  <select
                    value={uploadSourceId}
                    onChange={(event) => setUploadSourceId(event.target.value)}
                  >
                    <option value="">No source</option>
                    {sources.map((source) => (
                      <option key={source.id} value={source.id}>
                        {source.name}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  className="secondary-action"
                  disabled={!selectedDomainId || isUploadingFile}
                  type="submit"
                >
                  <FileSearch aria-hidden="true" />
                  {isUploadingFile ? "Queueing upload" : "Queue upload"}
                </button>
              </form>
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
                (() => {
                  const evidenceAudit = evidenceAuditFor(queryResult);
                  const contradictionAudit = contradictionAuditFor(queryResult);
                  const multiHopAudit = multiHopAuditFor(queryResult);
                  const evidenceRoute = evidenceRouteFor(queryResult);
                  return (
                <>
                  <div className="result-meta">
                    <span>Job {queryJob?.status ?? "unknown"}</span>
                    <span>{queryResult.runtime}</span>
                    <span>{queryResult.model}</span>
                    <span>{queryResult.citations.length} citations</span>
                  </div>
                  <div className="result-meta budget-meta" aria-label="Query budget usage">
                    <span>{queryResult.usage.within_budget ? "Within budget" : "Budget exceeded"}</span>
                    <span>
                      {evidenceAudit.grounded ? "Evidence linked" : "Evidence missing"}{" "}
                      {evidenceAudit.cited_segment_ids.length}/
                      {queryResult.citations.length}
                    </span>
                    <span>
                      {contradictionAudit.conflict_count === 0
                        ? "Contradictions 0"
                        : `Review ${contradictionAudit.conflict_count}`}
                    </span>
                    <span>
                      Searches {queryResult.usage.search_count}/
                      {queryResult.usage.budget.max_searches}
                    </span>
                    <span>
                      Citations {queryResult.usage.citation_count}/
                      {queryResult.usage.budget.max_citations}
                    </span>
                    <span>
                      Route {evidenceRoute.coverage_level.replaceAll("_", " ")}
                    </span>
                    <span>
                      Documents {evidenceRoute.document_count} / anchors{" "}
                      {evidenceRoute.anchor_count}
                    </span>
                    <span>
                      Evidence {queryResult.usage.evidence_tokens}/
                      {queryResult.usage.budget.max_evidence_tokens} tokens
                    </span>
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
                  <div className="evidence-route" aria-label="Evidence route">
                    <div className="route-summary">
                      <span className={evidenceRoute.multi_document ? "badge success" : "badge muted"}>
                        {evidenceRoute.multi_document ? "multi document" : "single document"}
                      </span>
                      <span className={evidenceRoute.has_neighbor_context ? "badge success" : "badge muted"}>
                        {evidenceRoute.has_neighbor_context ? "context expanded" : "no context"}
                      </span>
                      {evidenceRoute.warnings.map((warning) => (
                        <span className="badge warning" key={warning}>
                          {warning.replaceAll("_", " ")}
                        </span>
                      ))}
                    </div>
                    {evidenceRoute.documents.length > 0 ? (
                      <div className="route-documents">
                        {evidenceRoute.documents.map((document) => (
                          <article className="route-document" key={document.document_id}>
                            <strong>{document.title}</strong>
                            <span>
                              {document.segment_ids.length} segments /{" "}
                              {document.anchors.length} anchors
                            </span>
                          </article>
                        ))}
                      </div>
                    ) : null}
                  </div>
                  <div className="evidence-route multi-hop-audit" aria-label="Multi-hop audit">
                    <div className="route-summary">
                      <span
                        className={
                          multiHopAudit.status === "supported_multi_document"
                            ? "badge success"
                            : multiHopAudit.requires_multi_hop
                              ? "badge warning"
                              : "badge muted"
                        }
                      >
                        {multiHopAudit.status.replaceAll("_", " ")}
                      </span>
                      <span className={multiHopAudit.requires_multi_hop ? "badge warning" : "badge muted"}>
                        {multiHopAudit.requires_multi_hop ? "multi-hop question" : "single-hop question"}
                      </span>
                      <span className={multiHopAudit.document_count > 1 ? "badge success" : "badge muted"}>
                        {multiHopAudit.document_count} documents
                      </span>
                      {multiHopAudit.warnings.map((warning) => (
                        <span className="badge warning" key={warning}>
                          {warning.replaceAll("_", " ")}
                        </span>
                      ))}
                    </div>
                    {multiHopAudit.bridge_terms.length > 0 ? (
                      <p className="audit-note">
                        Bridge terms: {multiHopAudit.bridge_terms.join(", ")}
                      </p>
                    ) : null}
                  </div>
                  {(queryResult.neighbor_context ?? []).length > 0 ? (
                    <div className="citation-list neighbor-list" aria-label="Neighbor context">
                      {(queryResult.neighbor_context ?? []).map((context) => (
                        <article className="citation-row" key={context.segment_id}>
                          <div>
                            <strong>{context.title}</strong>
                            <span>
                              {context.anchor ?? "No anchor"} near{" "}
                              {context.source_segment_id.slice(0, 8)}
                            </span>
                          </div>
                          <p>{context.text}</p>
                          <span className="badge muted">
                            {context.token_count} tokens
                          </span>
                        </article>
                      ))}
                    </div>
                  ) : null}
                </>
                  );
                })()
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
              {lastProgressCursor ? (
                <span className="resume-cursor">Resume {lastProgressCursor.slice(0, 18)}</span>
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

          <article className="panel wide" id="evals">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Quality</p>
                <h2>Local evals</h2>
              </div>
              <span className={evalReport?.passed ? "status-pill local" : "status-pill"}>
                {evalReport ? (evalReport.passed ? "Passing" : "Failing") : "Not run"}
              </span>
            </div>
            <div className="eval-toolbar">
              <button
                className="secondary-action"
                disabled={isAnyEvalRunning}
                type="button"
                onClick={() => void handleRunSmokeEval()}
              >
                <CheckCircle2 aria-hidden="true" />
                {isRunningEval ? "Running eval smoke" : "Run eval smoke"}
              </button>
              {evalJob ? (
                <div className="selected-domain">
                  <span>Eval job</span>
                  <strong>
                    {evalJob.kind} {evalJob.status}
                  </strong>
                </div>
              ) : null}
            </div>
            <form className="eval-dataset-form" onSubmit={(event) => void handleRunSquadEval(event)}>
              <label className="span-two">
                SQuAD dataset path
                <input
                  aria-label="SQuAD dataset path"
                  value={squadDatasetPath}
                  onChange={(event) => setSquadDatasetPath(event.target.value)}
                  placeholder="dev-v2.0.json"
                />
              </label>
              <label>
                Max cases
                <input
                  aria-label="SQuAD max cases"
                  inputMode="numeric"
                  min="1"
                  max="1000"
                  type="number"
                  value={squadMaxCases}
                  onChange={(event) => setSquadMaxCases(event.target.value)}
                />
              </label>
              <label>
                Report stem
                <input
                  aria-label="SQuAD report stem"
                  disabled={!squadWriteReport}
                  value={squadReportStem}
                  onChange={(event) => setSquadReportStem(event.target.value)}
                  placeholder="squad-v2-dev-50"
                />
              </label>
              <label className="checkbox-field">
                <input
                  aria-label="Write SQuAD reports"
                  checked={squadWriteReport}
                  type="checkbox"
                  onChange={(event) => setSquadWriteReport(event.target.checked)}
                />
                <span>Write reports</span>
              </label>
              <button
                className="secondary-action"
                disabled={isAnyEvalRunning}
                type="submit"
              >
                <FileSearch aria-hidden="true" />
                {isRunningSquadEval ? "Running SQuAD eval" : "Run SQuAD eval"}
              </button>
            </form>
            <form
              className="eval-dataset-form"
              onSubmit={(event) => void handleRunHotpotQAEval(event)}
            >
              <label className="span-two">
                HotpotQA dataset path
                <input
                  aria-label="HotpotQA dataset path"
                  value={hotpotqaDatasetPath}
                  onChange={(event) => setHotpotqaDatasetPath(event.target.value)}
                  placeholder="hotpot_dev_distractor_v1.json"
                />
              </label>
              <label>
                Max cases
                <input
                  aria-label="HotpotQA max cases"
                  inputMode="numeric"
                  min="1"
                  max="1000"
                  type="number"
                  value={hotpotqaMaxCases}
                  onChange={(event) => setHotpotqaMaxCases(event.target.value)}
                />
              </label>
              <label>
                Report stem
                <input
                  aria-label="HotpotQA report stem"
                  disabled={!hotpotqaWriteReport}
                  value={hotpotqaReportStem}
                  onChange={(event) => setHotpotqaReportStem(event.target.value)}
                  placeholder="hotpotqa-dev-50"
                />
              </label>
              <label className="checkbox-field">
                <input
                  aria-label="Write HotpotQA reports"
                  checked={hotpotqaWriteReport}
                  type="checkbox"
                  onChange={(event) => setHotpotqaWriteReport(event.target.checked)}
                />
                <span>Write reports</span>
              </label>
              <button
                className="secondary-action"
                disabled={isAnyEvalRunning}
                type="submit"
              >
                <FileSearch aria-hidden="true" />
                {isRunningHotpotQAEval ? "Running HotpotQA eval" : "Run HotpotQA eval"}
              </button>
            </form>
            <form
              className="eval-dataset-form"
              onSubmit={(event) => void handleRunNaturalQuestionsEval(event)}
            >
              <label className="span-two">
                Natural Questions dataset path
                <input
                  aria-label="Natural Questions dataset path"
                  value={naturalQuestionsDatasetPath}
                  onChange={(event) => setNaturalQuestionsDatasetPath(event.target.value)}
                  placeholder="nq-dev-sample.jsonl"
                />
              </label>
              <label>
                Max cases
                <input
                  aria-label="Natural Questions max cases"
                  inputMode="numeric"
                  min="1"
                  max="1000"
                  type="number"
                  value={naturalQuestionsMaxCases}
                  onChange={(event) => setNaturalQuestionsMaxCases(event.target.value)}
                />
              </label>
              <label>
                Report stem
                <input
                  aria-label="Natural Questions report stem"
                  disabled={!naturalQuestionsWriteReport}
                  value={naturalQuestionsReportStem}
                  onChange={(event) => setNaturalQuestionsReportStem(event.target.value)}
                  placeholder="natural-questions-dev-50"
                />
              </label>
              <label className="checkbox-field">
                <input
                  aria-label="Write Natural Questions reports"
                  checked={naturalQuestionsWriteReport}
                  type="checkbox"
                  onChange={(event) => setNaturalQuestionsWriteReport(event.target.checked)}
                />
                <span>Write reports</span>
              </label>
              <button
                className="secondary-action"
                disabled={isAnyEvalRunning}
                type="submit"
              >
                <FileSearch aria-hidden="true" />
                {isRunningNaturalQuestionsEval
                  ? "Running Natural Questions eval"
                  : "Run Natural Questions eval"}
              </button>
            </form>
            <form
              className="eval-dataset-form"
              onSubmit={(event) => void handleRunOcrBenchmarkEval(event)}
            >
              <label className="span-two">
                OCR benchmark path
                <input
                  aria-label="OCR benchmark path"
                  value={ocrBenchmarkDatasetPath}
                  onChange={(event) => setOcrBenchmarkDatasetPath(event.target.value)}
                  placeholder="ocr-benchmark/manifest.json"
                />
              </label>
              <label>
                Format
                <select
                  aria-label="OCR benchmark format"
                  value={ocrBenchmarkFormat}
                  onChange={(event) => setOcrBenchmarkFormat(event.target.value)}
                >
                  <option value="manifest">Manifest</option>
                  <option value="funsd">FUNSD</option>
                  <option value="sroie">SROIE</option>
                </select>
              </label>
              <label>
                Max cases
                <input
                  aria-label="OCR benchmark max cases"
                  inputMode="numeric"
                  min="1"
                  max="1000"
                  type="number"
                  value={ocrBenchmarkMaxCases}
                  onChange={(event) => setOcrBenchmarkMaxCases(event.target.value)}
                />
              </label>
              <label>
                Report stem
                <input
                  aria-label="OCR benchmark report stem"
                  disabled={!ocrBenchmarkWriteReport}
                  value={ocrBenchmarkReportStem}
                  onChange={(event) => setOcrBenchmarkReportStem(event.target.value)}
                  placeholder="ocr-benchmark-25"
                />
              </label>
              <label className="checkbox-field">
                <input
                  aria-label="Write OCR benchmark reports"
                  checked={ocrBenchmarkWriteReport}
                  type="checkbox"
                  onChange={(event) => setOcrBenchmarkWriteReport(event.target.checked)}
                />
                <span>Write reports</span>
              </label>
              <button
                className="secondary-action"
                disabled={isAnyEvalRunning}
                type="submit"
              >
                <FileSearch aria-hidden="true" />
                {isRunningOcrBenchmarkEval
                  ? "Running OCR benchmark"
                  : "Run OCR benchmark"}
              </button>
            </form>
            {evalError ? (
              <p className="inline-error" role="alert">
                {evalError}
              </p>
            ) : null}
            <section className="eval-result" aria-label="Eval smoke results" aria-live="polite">
              {evalReport ? (
                <>
                  <div className="eval-metrics" aria-label="Eval metrics">
                    {Object.entries(evalReport.metrics).map(([name, value]) => (
                      <article className="eval-metric" key={name}>
                        <span>{name.replaceAll("_", " ")}</span>
                        <strong>{formatScore(value)}</strong>
                      </article>
                    ))}
                  </div>
                  {evalMetadataEntries(evalReport).length > 0 ? (
                    <div className="eval-metadata" aria-label="Eval metadata">
                      {evalMetadataEntries(evalReport).map(([name, value]) => (
                        <div key={name}>
                          <span>{name}</span>
                          <strong>{value}</strong>
                        </div>
                      ))}
                    </div>
                  ) : null}
                  <div className="eval-case-list" aria-label="Eval cases">
                    {evalReport.cases.map((evalCase) => (
                      <article className="eval-case-row" key={evalCase.case_id}>
                        <div>
                          <span className={evalCase.passed ? "badge success" : "badge warning"}>
                            {evalCase.passed ? "pass" : "fail"}
                          </span>
                          <strong>{evalCase.case_id}</strong>
                          <span>
                            {evalCase.question ??
                              `CER ${formatScore(evalCase.character_error_rate ?? 0)} / WER ${formatScore(
                                evalCase.word_error_rate ?? 0,
                              )}`}
                          </span>
                        </div>
                        <div className="provider-badges">
                          <span className="badge muted">
                            {(evalCase.citations ?? []).length} citations
                          </span>
                          <span className="badge muted">
                            {evalCase.failures.length ? evalCase.failures.join(", ") : "no failures"}
                          </span>
                        </div>
                      </article>
                    ))}
                  </div>
                  {evalReportPaths ? (
                    <div className="eval-report-paths" aria-label="Eval report paths">
                      <div>
                        <span>JSON report</span>
                        <strong>{evalReportPaths.json}</strong>
                      </div>
                      <div>
                        <span>Markdown report</span>
                        <strong>{evalReportPaths.markdown}</strong>
                      </div>
                    </div>
                  ) : null}
                </>
              ) : (
                <div className="empty-state compact">
                  <CheckCircle2 aria-hidden="true" />
                  <p>Run the local smoke eval to verify retrieval, citations, grounding, abstention, and budget compliance.</p>
                </div>
              )}
            </section>
            <section className="eval-history" aria-label="Eval run history">
              <div className="section-heading">
                <h3>Run history</h3>
                <div className="section-actions">
                  <button
                    className="secondary-action compact-action"
                    type="button"
                    disabled={isAnyEvalRunning || isComparingEvals || comparableEvalRuns.length < 2}
                    onClick={() => void handleCompareLatestEvals()}
                  >
                    <GitCompare aria-hidden="true" />
                    {isComparingEvals ? "Comparing" : "Compare latest"}
                  </button>
                  <button
                    className="icon-button"
                    type="button"
                    aria-label="Refresh eval history"
                    onClick={() => void refreshEvalRuns()}
                  >
                    <RefreshCw aria-hidden="true" />
                  </button>
                </div>
              </div>
              {evalComparison ? (
                <div className="eval-comparison" aria-label="Eval comparison" aria-live="polite">
                  <div className="comparison-summary">
                    <div>
                      <span>Baseline</span>
                      <strong>{evalComparison.baseline.suite_name}</strong>
                      <small>{evalComparison.baseline.case_count} cases</small>
                    </div>
                    <div>
                      <span>Candidate</span>
                      <strong>{evalComparison.candidate.suite_name}</strong>
                      <small>{evalComparison.candidate.case_count} cases</small>
                    </div>
                    <div>
                      <span>Average delta</span>
                      <strong>{formatDelta(evalComparison.average_delta)}</strong>
                      <small>{evalComparison.status}</small>
                    </div>
                  </div>
                  <div className="comparison-metrics">
                    <div className="comparison-metric comparison-header">
                      <strong>Metric</strong>
                      <span>Baseline</span>
                      <span>Candidate</span>
                      <span>Delta</span>
                    </div>
                    {evalComparison.metrics.map((metric) => (
                      <article className="comparison-metric" key={metric.name}>
                        <strong>{metric.name.replaceAll("_", " ")}</strong>
                        <span>{formatScore(metric.baseline)}</span>
                        <span>{formatScore(metric.candidate)}</span>
                        <span className={metric.delta < 0 ? "delta negative" : "delta"}>
                          {formatDelta(metric.delta)}
                        </span>
                      </article>
                    ))}
                  </div>
                </div>
              ) : null}
              {evalRuns.length > 0 ? (
                <div className="eval-run-list">
                  {evalRuns.map((run) => {
                    const metrics = run.report ? Object.values(run.report.metrics) : [];
                    const averageScore =
                      metrics.length > 0
                        ? formatScore(metrics.reduce((total, value) => total + value, 0) / metrics.length)
                        : "No report";
                    const isRerunning = rerunningEvalJobId === run.job.id;
                    return (
                      <article className="eval-run-row" key={run.job.id}>
                        <div>
                          <span className={run.job.status === "succeeded" ? "badge success" : "badge warning"}>
                            {run.job.status}
                          </span>
                          <strong>{run.report?.suite_name ?? "retos-smoke"}</strong>
                          <span>{formatDateTime(run.job.completed_at ?? run.job.updated_at)}</span>
                        </div>
                        <div className="provider-badges">
                          <span className="badge muted">{run.report?.case_count ?? 0} cases</span>
                          <span className="badge muted">{averageScore}</span>
                          <button
                            className="secondary-action compact-action"
                            type="button"
                            disabled={isAnyEvalRunning}
                            aria-label={`Rerun ${run.report?.suite_name ?? run.job.id}`}
                            onClick={() => void handleRerunEval(run.job.id)}
                          >
                            <RefreshCw aria-hidden="true" />
                            {isRerunning ? "Rerunning" : "Rerun"}
                          </button>
                        </div>
                      </article>
                    );
                  })}
                </div>
              ) : (
                <div className="empty-state compact">
                  <Activity aria-hidden="true" />
                  <p>No eval runs have been recorded yet.</p>
                </div>
              )}
            </section>
            {evalTrends.length > 0 ? (
              <section className="eval-trends" aria-label="Eval trends">
                {evalTrends.map((trend) => (
                  <article className="eval-trend-card" key={trend.suite_name}>
                    <div className="trend-heading">
                      <div>
                        <strong>{trend.suite_name}</strong>
                        <span>{trend.run_count} runs</span>
                      </div>
                      <span className={trend.latest.passed ? "badge success" : "badge warning"}>
                        {formatScore(trend.pass_rate)} pass
                      </span>
                    </div>
                    <div className="trend-metric-list">
                      {trend.metrics.slice(0, 5).map((metric) => (
                        <div className="trend-metric-row" key={metric.name}>
                          <span>{metric.name.replaceAll("_", " ")}</span>
                          <strong>{formatScore(metric.latest)}</strong>
                          <small className={`delta ${metric.direction}`}>
                            {formatDelta(metric.delta)}
                          </small>
                        </div>
                      ))}
                    </div>
                    <span className="trend-updated">
                      Latest {formatDateTime(trend.latest.completed_at)}
                    </span>
                  </article>
                ))}
              </section>
            ) : null}
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

            <section className="admin-users" aria-label="Admin users">
              <div className="section-heading">
                <h3>Admin users</h3>
                <button
                  className="icon-button"
                  type="button"
                  aria-label="Refresh admin users"
                  onClick={() => void refreshAdminUsers()}
                >
                  <RefreshCw aria-hidden="true" />
                </button>
              </div>
              <form className="admin-user-form" onSubmit={(event) => void handleCreateAdminUser(event)}>
                <label>
                  <span>Email</span>
                  <input
                    aria-label="New admin email"
                    autoComplete="off"
                    type="email"
                    value={adminUserEmail}
                    onChange={(event) => setAdminUserEmail(event.target.value)}
                  />
                </label>
                <label>
                  <span>Password</span>
                  <input
                    aria-label="New admin password"
                    autoComplete="new-password"
                    type="password"
                    value={adminUserPassword}
                    onChange={(event) => setAdminUserPassword(event.target.value)}
                  />
                </label>
                <label>
                  <span>Role</span>
                  <select
                    aria-label="New admin role"
                    value={adminUserRole}
                    onChange={(event) => setAdminUserRole(event.target.value)}
                  >
                    <option value="admin">Admin</option>
                    <option value="viewer">Viewer</option>
                  </select>
                </label>
                <button
                  className="secondary-action"
                  disabled={isCreatingAdminUser || !token}
                  type="submit"
                >
                  <UserPlus aria-hidden="true" />
                  {isCreatingAdminUser ? "Creating admin" : "Create admin"}
                </button>
              </form>
              {adminUserError ? (
                <p className="inline-error" role="alert">
                  {adminUserError}
                </p>
              ) : null}
              {adminUserMessage ? (
                <p className="inline-success compact-success" role="status">
                  {adminUserMessage}
                </p>
              ) : null}
              <div className="admin-user-list">
                {adminUsers.map((user) => (
                  <article className="admin-user-row" key={user.id}>
                    <div>
                      <span className={user.is_active ? "badge success" : "badge muted"}>
                        {user.is_active ? "active" : "inactive"}
                      </span>
                      <strong>{user.email}</strong>
                      <span>{user.roles.join(", ")}</span>
                      <span>{formatDateTime(user.updated_at)}</span>
                    </div>
                    <div className="admin-domain-grants" aria-label={`Domain grants for ${user.email}`}>
                      <div className="grant-list">
                        {(adminDomainGrants[user.id] ?? []).map((grant) => {
                          const grantedDomain = domainById.get(grant.domain_id);
                          return (
                            <span className="grant-chip" key={grant.id}>
                              {grantedDomain?.slug ?? grant.domain_id}
                              <button
                                type="button"
                                aria-label={`Revoke ${grantedDomain?.slug ?? grant.domain_id} from ${user.email}`}
                                disabled={savingAdminUserId === user.id}
                                onClick={() => void handleDeleteDomainGrant(user, grant.domain_id)}
                              >
                                <X aria-hidden="true" />
                              </button>
                            </span>
                          );
                        })}
                        {(adminDomainGrants[user.id] ?? []).length === 0 ? (
                          <span className="muted-inline">No domain grants</span>
                        ) : null}
                      </div>
                      <form
                        className="grant-form"
                        onSubmit={(event) => void handleCreateDomainGrant(event, user)}
                      >
                        <label>
                          <span>Grant domain</span>
                          <select
                            aria-label={`Grant domain to ${user.email}`}
                            value={adminGrantDomainIds[user.id] ?? ""}
                            onChange={(event) =>
                              setAdminGrantDomainIds((current) => ({
                                ...current,
                                [user.id]: event.target.value,
                              }))
                            }
                          >
                            <option value="">Select domain</option>
                            {domains.map((domain) => (
                              <option key={domain.id} value={domain.id}>
                                {domain.slug}
                              </option>
                            ))}
                          </select>
                        </label>
                        <button
                          className="ghost-action"
                          disabled={savingAdminUserId === user.id || domains.length === 0}
                          type="submit"
                        >
                          <Check aria-hidden="true" />
                          Grant
                        </button>
                      </form>
                    </div>
                    <div className="admin-user-actions">
                      <button
                        className="ghost-action"
                        disabled={savingAdminUserId === user.id || user.email === email.trim().toLowerCase()}
                        type="button"
                        onClick={() => void handleUpdateAdminUserStatus(user)}
                      >
                        <Power aria-hidden="true" />
                        {user.is_active ? "Deactivate" : "Activate"}
                      </button>
                      <form onSubmit={(event) => void handleResetAdminPassword(event, user)}>
                        <input
                          aria-label={`New password for ${user.email}`}
                          autoComplete="new-password"
                          placeholder="New password"
                          type="password"
                          value={adminPasswordResets[user.id] ?? ""}
                          onChange={(event) =>
                            setAdminPasswordResets((current) => ({
                              ...current,
                              [user.id]: event.target.value,
                            }))
                          }
                        />
                        <button
                          className="ghost-action"
                          disabled={savingAdminUserId === user.id}
                          type="submit"
                        >
                          <KeyRound aria-hidden="true" />
                          Reset
                        </button>
                      </form>
                    </div>
                  </article>
                ))}
                {adminUsers.length === 0 ? (
                  <div className="empty-state compact">
                    <Users aria-hidden="true" />
                    <p>Connect an admin session to manage local admin accounts.</p>
                  </div>
                ) : null}
              </div>
            </section>
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
                  <option value="eval.run">Evals</option>
                  <option value="agent.query">Agent queries</option>
                </select>
              </label>
              <button
                className="ghost-action"
                disabled={isLoadingAudit}
                type="button"
                onClick={() => void refreshAudit()}
              >
                <RefreshCw aria-hidden="true" />
                {isLoadingAudit ? "Refreshing audit" : "Refresh audit"}
              </button>
              <button
                className="ghost-action"
                disabled={isExportingAudit}
                type="button"
                onClick={() => void handleExportAudit()}
              >
                <Download aria-hidden="true" />
                {isExportingAudit ? "Exporting audit" : "Export audit"}
              </button>
            </div>
            {auditError ? (
              <p className="inline-error" role="alert">
                {auditError}
              </p>
            ) : null}
            {auditExportMessage ? (
              <p className="inline-success" role="status">
                {auditExportMessage}
              </p>
            ) : null}
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
                  <button
                    className="ghost-action job-inspect-action"
                    disabled={isLoadingJobDetail && selectedJobId === job.id}
                    type="button"
                    onClick={() => void handleInspectJob(job.id)}
                  >
                    <Eye aria-hidden="true" />
                    {isLoadingJobDetail && selectedJobId === job.id ? "Inspecting" : "Inspect"}
                  </button>
                  {job.status === "failed" || job.status === "cancelled" ? (
                    <button
                      className="ghost-action job-retry-action"
                      disabled={retryingJobId === job.id}
                      type="button"
                      onClick={() => void handleRetryJob(job.id)}
                    >
                      <RotateCcw aria-hidden="true" />
                      {retryingJobId === job.id ? "Retrying" : "Retry"}
                    </button>
                  ) : null}
                </article>
              ))}
              {filteredJobs.length === 0 ? (
                <div className="empty-state compact">
                  <LockKeyhole aria-hidden="true" />
                  <p>No jobs match this filter yet.</p>
                </div>
              ) : null}
            </div>
            {selectedJobId ? (
              <section className="job-detail-panel" aria-label="Selected job detail">
                <div className="section-heading compact">
                  <div>
                    <h3>Job detail</h3>
                    <span>{selectedJobId}</span>
                  </div>
                  <button
                    className="ghost-action compact-action"
                    type="button"
                    onClick={handleCloseJobDetail}
                  >
                    <X aria-hidden="true" />
                    Close
                  </button>
                </div>
                {jobDetailError ? (
                  <p className="inline-error" role="alert">
                    {jobDetailError}
                  </p>
                ) : null}
                {selectedJob ? (
                  <>
                    <div className="job-detail-grid">
                      <div>
                        <span>Status</span>
                        <strong>{selectedJob.status}</strong>
                      </div>
                      <div>
                        <span>Kind</span>
                        <strong>{selectedJob.kind}</strong>
                      </div>
                      <div>
                        <span>Domain</span>
                        <strong>{selectedJob.domain_id ?? "none"}</strong>
                      </div>
                      <div>
                        <span>Source</span>
                        <strong>{selectedJob.source_id ?? "none"}</strong>
                      </div>
                      <div>
                        <span>Started</span>
                        <strong>{formatDateTime(selectedJob.started_at)}</strong>
                      </div>
                      <div>
                        <span>Updated</span>
                        <strong>{formatDateTime(selectedJob.updated_at)}</strong>
                      </div>
                    </div>
                    {selectedJob.error ? (
                      <p className="inline-error" role="alert">
                        {selectedJob.error}
                      </p>
                    ) : null}
                    <div className="job-detail-columns">
                      <div>
                        <span>Payload</span>
                        <pre>{JSON.stringify(selectedJob.payload, null, 2)}</pre>
                      </div>
                      <div>
                        <span>Persisted progress</span>
                        {selectedJobProgressEvents.length > 0 ? (
                          <ol className="job-detail-timeline">
                            {selectedJobProgressEvents.map((event) => (
                              <li key={event.id}>
                                <strong>{event.event_type}</strong>
                                <span>{formatDateTime(event.occurred_at)}</span>
                                <p>{event.message}</p>
                              </li>
                            ))}
                          </ol>
                        ) : (
                          <p className="payload-summary">
                            No persisted progress is loaded for this job.
                          </p>
                        )}
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="empty-state compact">
                    <Activity aria-hidden="true" />
                    <p>
                      {isLoadingJobDetail
                        ? "Loading job detail."
                        : "Select a job to inspect it."}
                    </p>
                  </div>
                )}
              </section>
            ) : null}
            <section className="job-progress-groups" aria-label="Progress grouped by job">
              <div className="section-heading compact">
                <h3>Progress by job</h3>
                <span className="badge muted">{progressGroups.length}</span>
              </div>
              <div className="job-progress-list">
                {progressGroups.map((group) => (
                  <article className="job-progress-row" key={group.jobId}>
                    <div className="job-progress-main">
                      <span
                        className={`badge ${group.status === "failed" ? "warning" : "muted"}`}
                      >
                        {group.status}
                      </span>
                      <div>
                        <strong>{group.kind}</strong>
                        <span>{group.jobId}</span>
                      </div>
                    </div>
                    <div className="job-progress-meta">
                      <div>
                        <span>Events</span>
                        <strong>{group.eventCount}</strong>
                      </div>
                      <div>
                        <span>Last event</span>
                        <strong>{group.lastEventType}</strong>
                      </div>
                      <div>
                        <span>Last update</span>
                        <strong>{formatDateTime(group.lastOccurredAt)}</strong>
                      </div>
                    </div>
                    <p className="payload-summary">{group.lastMessage}</p>
                  </article>
                ))}
                {progressGroups.length === 0 ? (
                  <div className="empty-state compact">
                    <Activity aria-hidden="true" />
                    <p>No job progress groups have been loaded yet.</p>
                  </div>
                ) : null}
              </div>
            </section>
            <div className="audit-event-grid">
              <section className="audit-event-panel" aria-label="Journal events">
                <div className="section-heading compact">
                  <h3>Journal events</h3>
                  <span className="badge muted">{journalEvents.length}</span>
                </div>
                <div className="audit-event-list">
                  {journalEvents.map((event) => (
                    <article className="audit-event-row" key={event.id}>
                      <div>
                        <strong>{event.event_type}</strong>
                        <span>
                          {event.entity_type} {event.entity_id}
                        </span>
                      </div>
                      <div>
                        <span>{event.actor}</span>
                        <span>{formatDateTime(event.occurred_at)}</span>
                      </div>
                      <p className="payload-summary">{summarizePayload(event.payload)}</p>
                    </article>
                  ))}
                  {journalEvents.length === 0 ? (
                    <div className="empty-state compact">
                      <LockKeyhole aria-hidden="true" />
                      <p>No journal events have been loaded yet.</p>
                    </div>
                  ) : null}
                </div>
              </section>
              <section className="audit-event-panel" aria-label="Persisted progress events">
                <div className="section-heading compact">
                  <h3>Persisted progress</h3>
                  <span className="badge muted">{auditProgressEvents.length}</span>
                </div>
                <div className="audit-event-list">
                  {auditProgressEvents.map((event) => (
                    <article className="audit-event-row" key={event.id}>
                      <div>
                        <strong>{event.event_type}</strong>
                        <span>{event.message}</span>
                      </div>
                      <div>
                        <span>{event.job_id ?? "system"}</span>
                        <span>{formatDateTime(event.occurred_at)}</span>
                      </div>
                      <p className="payload-summary">{summarizePayload(event.payload)}</p>
                    </article>
                  ))}
                  {auditProgressEvents.length === 0 ? (
                    <div className="empty-state compact">
                      <Activity aria-hidden="true" />
                      <p>No persisted progress events have been loaded yet.</p>
                    </div>
                  ) : null}
                </div>
              </section>
            </div>
          </article>
        </section>
      </section>
    </main>
  );
}

export default App;
