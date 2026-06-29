import { createHash } from "node:crypto";
import { mkdir, readFile, stat, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { expect, type Page, test } from "@playwright/test";

const VISUAL_AUDIT_DIR = resolve(process.cwd(), "visual-audit");

async function visualAuditRecord(
  name: string,
  path: string,
  viewport: { width: number; height: number },
) {
  const [file, metadata] = await Promise.all([readFile(path), stat(path)]);
  return {
    name,
    path: path.replace(`${process.cwd()}/`, ""),
    sha256: createHash("sha256").update(file).digest("hex"),
    size_bytes: metadata.size,
    viewport,
  };
}

function jobFixture(
  id: string,
  kind: string,
  status: string,
  payload: Record<string, unknown> = {},
  domainId: string | null = "domain-123",
) {
  return {
    id,
    kind,
    status,
    domain_id: domainId,
    source_id: null,
    payload,
    error: null,
    started_at: null,
    completed_at: status === "succeeded" ? "2026-06-27T00:01:00Z" : null,
    created_at: "2026-06-27T00:00:00Z",
    updated_at: "2026-06-27T00:00:00Z",
  };
}

async function mockProviderApi(page: Page) {
  const domains = [
    {
      id: "domain-123",
      slug: "smoke-research",
      name: "Smoke Research",
      description: "A smoke-test domain",
      archived_at: null,
      created_at: "2026-06-27T00:00:00Z",
      updated_at: "2026-06-27T00:00:00Z",
    },
  ];
  const sources = [
    {
      id: "source-123",
      domain_id: "domain-123",
      kind: "mount",
      name: "Mounted Corpus",
      uri: "file:///corpus/smoke",
      created_at: "2026-06-27T00:00:00Z",
      updated_at: "2026-06-27T00:00:00Z",
    },
  ];
  const documents = [
    {
      id: "document-1",
      domain_id: "domain-123",
      source_id: null,
      external_id: "smoke-doc",
      title: "Smoke Document",
      content_hash: "abcdef1234567890",
      metadata: {},
      source_uri: "memory://smoke-doc",
      size_bytes: 128,
      archived_at: null,
      created_at: "2026-06-27T00:00:00Z",
      updated_at: "2026-06-27T00:00:00Z",
    },
  ];
  const demoDomain = {
    id: "domain-demo",
    slug: "retos-demo",
    name: "RetOS Demo",
    description: "Local seeded corpus for evaluating RetOS document workflows.",
    archived_at: null,
    created_at: "2026-06-27T00:08:00Z",
    updated_at: "2026-06-27T00:08:00Z",
  };
  const demoSource = {
    id: "source-demo",
    domain_id: demoDomain.id,
    kind: "upload",
    name: "Local demo fixtures",
    uri: "demo://retos/local-fixtures",
    created_at: "2026-06-27T00:08:00Z",
    updated_at: "2026-06-27T00:08:00Z",
  };
  const demoDocuments = [
    {
      id: "document-demo-apollo",
      domain_id: demoDomain.id,
      source_id: demoSource.id,
      external_id: "retos-demo-apollo-guidance",
      title: "Apollo Guidance Notes",
      content_hash: "demoapollo1234567890",
      metadata: { seed: "retos-demo" },
      source_uri: "demo://retos/local-fixtures/retos-demo-apollo-guidance.txt",
      size_bytes: 192,
      archived_at: null,
      created_at: "2026-06-27T00:08:00Z",
      updated_at: "2026-06-27T00:08:00Z",
    },
    {
      id: "document-demo-incident",
      domain_id: demoDomain.id,
      source_id: demoSource.id,
      external_id: "retos-demo-incident-policy",
      title: "Incident Retention Policy",
      content_hash: "demoincident123456",
      metadata: { seed: "retos-demo" },
      source_uri: "demo://retos/local-fixtures/retos-demo-incident-policy.txt",
      size_bytes: 184,
      archived_at: null,
      created_at: "2026-06-27T00:08:00Z",
      updated_at: "2026-06-27T00:08:00Z",
    },
  ];
  const documentVersions = [
    {
      id: "version-1",
      document_id: "document-1",
      version: 1,
      source_uri: "memory://smoke-doc",
      content_hash: "abcdef1234567890",
      size_bytes: 128,
      created_at: "2026-06-27T00:00:00Z",
    },
  ];
  const artifacts = [
    {
      id: "artifact-1",
      document_version_id: "version-1",
      kind: "raw_text",
      uri: "memory://smoke-doc#raw-text",
      sha256: "abcdef1234567890",
      size_bytes: 48,
      created_at: "2026-06-27T00:00:00Z",
    },
  ];
  const segments = [
    {
      id: "segment-1234567890",
      document_version_id: "version-1",
      ordinal: 1,
      text: "Smoke segment text for search readiness.",
      anchor: "page=1",
      token_count: 6,
      content_hash: "1234567890abcdef",
      created_at: "2026-06-27T00:00:00Z",
    },
    {
      id: "segment-neighbor-1",
      document_version_id: "version-1",
      ordinal: 2,
      text: "Adjacent context explains who reviewed the search readiness evidence.",
      anchor: "page=2",
      token_count: 9,
      content_hash: "fedcba0987654321",
      created_at: "2026-06-27T00:00:00Z",
    },
  ];
  const failedIndexJob = {
    ...jobFixture("job-failed-index-1", "index.domain", "failed", {
      requested_at: "fixture",
    }),
    error: "fixture failure",
    completed_at: "2026-06-27T00:01:00Z",
  };
  const jobs = [jobFixture("job-seed-1", "ingest.source", "succeeded"), failedIndexJob];
  const auditHashFields = {
    payload_hash: "1111111111111111111111111111111111111111111111111111111111111111",
    prev_hash: null,
    event_hash: "2222222222222222222222222222222222222222222222222222222222222222",
  };
  const journalEvents = [
    {
      id: "journal-seed-1",
      trace_id: "job-seed-1",
      ...auditHashFields,
      occurred_at: "2026-06-27T00:00:00Z",
      actor: "admin@retos.dev",
      event_type: "job.created",
      entity_type: "job",
      entity_id: "job-seed-1",
      payload: { kind: "ingest.source", status: "succeeded" },
    },
  ];
  const progressEvents = [
    {
      id: "progress-seed-1",
      trace_id: "job-seed-1",
      payload_hash: "3333333333333333333333333333333333333333333333333333333333333333",
      prev_hash: auditHashFields.event_hash,
      event_hash: "4444444444444444444444444444444444444444444444444444444444444444",
      job_id: "job-seed-1",
      occurred_at: "2026-06-27T00:00:00Z",
      event_type: "job.queued",
      message: "Queued ingest.source",
      payload: { status: "queued" },
    },
  ];
  const evalReport = {
    suite_name: "retos-smoke",
    passed: true,
    case_count: 3,
    metadata: {
      source: "built-in",
      dataset: "retos-smoke-fixtures",
    },
    metrics: {
      retrieval_recall: 1,
      citation_validity: 1,
      grounded_answer: 1,
      abstention: 1,
      budget_compliance: 1,
    },
    cases: [
      {
        case_id: "apollo-guidance",
        question: "What did Apollo guidance computers use for mission operations?",
        passed: true,
        retrieval_recall: true,
        citation_validity: true,
        grounded_answer: true,
        abstention: true,
        budget_compliance: true,
        answer: "Grounded answer for Apollo guidance computers.",
        citations: [{ title: "Apollo Guidance Notes" }],
        failures: [],
      },
      {
        case_id: "marine-salinity",
        question: "Which notes mention salinity and plankton?",
        passed: true,
        retrieval_recall: true,
        citation_validity: true,
        grounded_answer: true,
        abstention: true,
        budget_compliance: true,
        answer: "Grounded answer for marine salinity.",
        citations: [{ title: "Marine Biology Notes" }],
        failures: [],
      },
      {
        case_id: "no-evidence",
        question: "Which document explains medieval ceramic kiln temperatures?",
        passed: true,
        retrieval_recall: true,
        citation_validity: true,
        grounded_answer: true,
        abstention: true,
        budget_compliance: true,
        answer: "I could not find enough indexed evidence to answer this question.",
        citations: [],
        failures: [],
      },
    ],
  };
  const squadReport = {
    ...evalReport,
    suite_name: "squad-v2",
    case_count: 2,
    metadata: {
      adapter: "squad-v2",
      dataset_path: "/evals/datasets/ui-squad.json",
      max_cases: 2,
      source: "api",
    },
    cases: [
      {
        ...evalReport.cases[0],
        case_id: "squad-mars-red-planet",
        question: "Why is Mars called the Red Planet?",
      },
      {
        ...evalReport.cases[2],
        case_id: "squad-mars-ocean-depth",
        question: "How deep are the oceans on Mars today?",
      },
    ],
  };
  const agentMultihopReport = {
    ...evalReport,
    suite_name: "agent-multihop",
    case_count: 3,
    metadata: {
      source: "built-in",
      dataset: "agent-multihop-fixtures",
    },
    metrics: {
      query_plan: 1,
      multi_hop_support: 1,
      evidence_route: 1,
      citation_validity: 1,
      grounded_answer: 1,
      budget_compliance: 1,
    },
    cases: [
      {
        ...evalReport.cases[0],
        case_id: "apollo-telemetry-bridge",
        question: "Compare Apollo checklist review and telemetry guidance",
      },
      {
        ...evalReport.cases[0],
        case_id: "invoice-retention-policy",
        question: "Compare invoice approval and retention policy evidence",
      },
      {
        ...evalReport.cases[0],
        case_id: "incident-escalation-triage",
        question:
          "Which same incident response evidence connects triage notes and escalation policy?",
      },
    ],
  };
  const hotpotqaReport = {
    ...evalReport,
    suite_name: "hotpotqa",
    case_count: 1,
    cases: [
      {
        ...evalReport.cases[0],
        case_id: "hotpotqa-vela-air-force",
        question: "Which agency operated Vela spacecraft?",
      },
    ],
  };
  const hotpotqaAgentReport = {
    ...agentMultihopReport,
    suite_name: "hotpotqa-agent",
    case_count: 1,
    metadata: {
      adapter: "hotpotqa-agent",
      dataset_path: "/var/lib/retos/evals/datasets/ui-hotpotqa.json",
      max_cases: 1,
      source: "api",
    },
    cases: [
      {
        ...agentMultihopReport.cases[0],
        case_id: "hotpotqa-agent-vela-air-force",
        question: "Compare HotpotQA supporting facts for Vela and United States Air Force.",
      },
    ],
  };
  const naturalQuestionsReport = {
    ...evalReport,
    suite_name: "natural-questions",
    case_count: 1,
    cases: [
      {
        ...evalReport.cases[0],
        case_id: "natural-questions-123",
        question: "Which star is Mercury closest to?",
      },
    ],
  };
  const ocrBenchmarkReport = {
    suite_name: "ocr-manifest",
    passed: true,
    case_count: 1,
    metrics: {
      character_error_rate: 0,
      word_error_rate: 0,
    },
    cases: [
      {
        case_id: "receipt-001",
        expected_text: "Receipt total 42",
        actual_text: "Receipt total 42",
        character_error_rate: 0,
        word_error_rate: 0,
        passed: true,
        failures: [],
      },
    ],
  };
  const evalRuns: {
    job: ReturnType<typeof jobFixture>;
    report: Record<string, unknown> | null;
  }[] = [];
  let evalRerunCount = 0;
  const adminUsers = [
    {
      id: "admin-user-1",
      email: "admin@retos.dev",
      roles: ["admin"],
      is_active: true,
      created_at: "2026-06-27T00:00:00Z",
      updated_at: "2026-06-27T00:00:00Z",
    },
  ];
  const domainGrants: Record<string, { id: string; admin_user_id: string; domain_id: string; created_at: string }[]> = {
    "admin-user-1": [],
  };
  const evalComparison = {
    baseline: {
      job_id: "job-eval-1",
      suite_name: "retos-smoke",
      passed: true,
      case_count: 3,
      completed_at: "2026-06-27T00:02:00Z",
    },
    candidate: {
      job_id: "job-eval-squad-1",
      suite_name: "squad-v2",
      passed: true,
      case_count: 2,
      completed_at: "2026-06-27T00:03:00Z",
    },
    metrics: [
      { name: "retrieval_recall", baseline: 1, candidate: 1, delta: 0 },
      { name: "citation_validity", baseline: 1, candidate: 1, delta: 0 },
      { name: "grounded_answer", baseline: 1, candidate: 1, delta: 0 },
      { name: "abstention", baseline: 1, candidate: 1, delta: 0 },
      { name: "budget_compliance", baseline: 1, candidate: 1, delta: 0 },
    ],
    average_delta: 0,
    status: "unchanged",
  };
  const evalRegressionGate = {
    passed: true,
    baseline: evalComparison.baseline,
    candidate: evalComparison.candidate,
    metric_drop_tolerance: 0.02,
    average_drop_tolerance: 0.01,
    average_normalized_delta: 0,
    regressions: [],
    metrics: evalComparison.metrics.map((metric) => ({
      ...metric,
      normalized_delta: metric.delta,
      direction: "higher_is_better",
      regressed: false,
    })),
  };

  function evalRunsForRequestUrl(url: string) {
    const domainId = new URL(url).searchParams.get("domain_id");
    return domainId ? evalRuns.filter((run) => run.job.domain_id === domainId) : evalRuns;
  }

  function buildEvalTrends(sourceRuns = evalRuns) {
    const grouped = new Map<string, typeof evalRuns>();
    for (const run of sourceRuns.slice().reverse()) {
      if (!run.report) {
        continue;
      }
      const suiteName = String(run.report.suite_name);
      grouped.set(suiteName, [...(grouped.get(suiteName) ?? []), run]);
    }
    return Array.from(grouped.entries()).map(([suiteName, runs]) => {
      const latest = runs[runs.length - 1];
      const metricNames = Array.from(
        new Set(
          runs.flatMap((run) =>
            Object.keys((run.report?.metrics as Record<string, number> | undefined) ?? {}),
          ),
        ),
      ).sort();
      return {
        suite_name: suiteName,
        run_count: runs.length,
        pass_rate: runs.filter((run) => run.report?.passed === true).length / runs.length,
        latest: {
          job_id: latest.job.id,
          suite_name: suiteName,
          passed: Boolean(latest.report?.passed),
          case_count: Number(latest.report?.case_count ?? 0),
          completed_at: latest.job.completed_at,
        },
        metrics: metricNames.map((name) => {
          const values = runs
            .map((run) => (run.report?.metrics as Record<string, number> | undefined)?.[name])
            .filter((value): value is number => typeof value === "number");
          const first = values[0];
          const latestValue = values[values.length - 1];
          const delta = latestValue - first;
          const lowerIsBetter = name.includes("error_rate");
          const direction =
            delta === 0
              ? "unchanged"
              : lowerIsBetter
                ? delta < 0
                  ? "improved"
                  : "regressed"
                : delta > 0
                  ? "improved"
                  : "regressed";
          return {
            name,
            first,
            latest: latestValue,
            delta,
            minimum: Math.min(...values),
            maximum: Math.max(...values),
            average: values.reduce((total, value) => total + value, 0) / values.length,
            direction,
          };
        }),
        points: runs.map((run) => ({
          job_id: run.job.id,
          suite_name: suiteName,
          passed: Boolean(run.report?.passed),
          case_count: Number(run.report?.case_count ?? 0),
          completed_at: run.job.completed_at,
          metrics: run.report?.metrics ?? {},
        })),
      };
    });
  }

  function recordAudit(job: ReturnType<typeof jobFixture>) {
    const baseTime = "2026-06-27T00:01:";
    journalEvents.unshift({
      id: `journal-${job.id}`,
      trace_id: job.id,
      occurred_at: `${baseTime}00Z`,
      actor: "admin@retos.dev",
      event_type: "job.created",
      entity_type: "job",
      entity_id: job.id,
      payload: { kind: job.kind, status: job.status },
    });
    progressEvents.unshift(
      {
        id: `progress-${job.id}-completed`,
        trace_id: job.id,
        job_id: job.id,
        occurred_at: `${baseTime}20Z`,
        event_type: `job.${job.status}`,
        message: `Completed ${job.kind}`,
        payload: { status: job.status },
      },
      {
        id: `progress-${job.id}-started`,
        trace_id: job.id,
        job_id: job.id,
        occurred_at: `${baseTime}10Z`,
        event_type: `${job.kind}.started`,
        message: `Started ${job.kind}`,
        payload: { status: "running" },
      },
      {
        id: `progress-${job.id}-queued`,
        trace_id: job.id,
        job_id: job.id,
        occurred_at: `${baseTime}00Z`,
        event_type: "job.queued",
        message: `Queued ${job.kind}`,
        payload: { status: "queued" },
      },
    );
  }

  function recordAdminAudit(adminUserId: string, eventType: string, email: string) {
    journalEvents.unshift({
      id: `journal-${eventType}-${adminUserId}`,
      trace_id: null,
      occurred_at: "2026-06-27T00:01:00Z",
      actor: "admin@retos.dev",
      event_type: eventType,
      entity_type: "admin_user",
      entity_id: adminUserId,
      payload: { email },
    });
  }

  function recordDomainGrantAudit(adminUserId: string, eventType: string, domainId: string) {
    journalEvents.unshift({
      id: `journal-${eventType}-${adminUserId}-${domainId}`,
      trace_id: null,
      occurred_at: "2026-06-27T00:01:00Z",
      actor: "admin@retos.dev",
      event_type: eventType,
      entity_type: "admin_user",
      entity_id: adminUserId,
      payload: { domain_id: domainId },
    });
  }

  await page.route("http://localhost:8000/demo/seed", async (route) => {
    if (!domains.some((domain) => domain.id === demoDomain.id)) {
      domains.push(demoDomain);
    }
    if (!sources.some((source) => source.id === demoSource.id)) {
      sources.push(demoSource);
    }
    for (const document of demoDocuments) {
      if (!documents.some((item) => item.id === document.id)) {
        documents.push(document);
      }
    }
    const indexJob = jobFixture("job-demo-index-1", "index.domain", "succeeded", {
      requested_by: "seed-demo",
      seed: "retos-demo",
    });
    jobs.unshift(indexJob);
    recordAudit(indexJob);
    await route.fulfill({
      contentType: "application/json",
      json: {
        domain_id: demoDomain.id,
        source_id: demoSource.id,
        created_documents: demoDocuments.length,
        skipped_documents: 0,
        index_job_id: indexJob.id,
        indexed_segments: 4,
      },
    });
  });

  await page.route("http://localhost:8000/auth/login", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: { access_token: "test-token", token_type: "bearer" },
    });
  });
  await page.route("http://localhost:8000/versionz", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: {
        service: "retos-api",
        version: "2026.06.29-local",
        revision: "abcdef1234567890",
        created: "2026-06-29T12:00:00Z",
      },
    });
  });
  await page.route("http://localhost:8000/readyz", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: {
        status: "ok",
        service: "retos-api",
        components: { database: "ok" },
      },
    });
  });
  await page.route("http://localhost:8000/admin/users", async (route) => {
    if (route.request().method() === "POST") {
      const payload = route.request().postDataJSON() as {
        email: string;
        password: string;
        roles: string[];
      };
      const created = {
        id: "admin-user-2",
        email: payload.email.toLowerCase(),
        roles: payload.roles,
        is_active: true,
        created_at: "2026-06-27T00:02:00Z",
        updated_at: "2026-06-27T00:02:00Z",
      };
      adminUsers.push(created);
      domainGrants[created.id] = [];
      recordAdminAudit(created.id, "admin_user.created", created.email);
      await route.fulfill({
        contentType: "application/json",
        status: 201,
        json: created,
      });
      return;
    }
    await route.fulfill({
      contentType: "application/json",
      json: adminUsers,
    });
  });
  await page.route(/http:\/\/localhost:8000\/admin\/users\/[^/]+\/domain-grants(?:\/[^/]+)?$/, async (route) => {
    const parts = new URL(route.request().url()).pathname.split("/");
    const adminUserId = parts[3];
    const domainId = parts[5];
    domainGrants[adminUserId] ??= [];
    if (route.request().method() === "POST") {
      const payload = route.request().postDataJSON() as { domain_id: string };
      const grant = {
        id: `grant-${adminUserId}-${payload.domain_id}`,
        admin_user_id: adminUserId,
        domain_id: payload.domain_id,
        created_at: "2026-06-27T00:05:00Z",
      };
      domainGrants[adminUserId] = [
        ...domainGrants[adminUserId].filter((item) => item.domain_id !== payload.domain_id),
        grant,
      ];
      recordDomainGrantAudit(adminUserId, "admin_user.domain_grant_created", payload.domain_id);
      await route.fulfill({ contentType: "application/json", status: 201, json: grant });
      return;
    }
    if (route.request().method() === "DELETE" && domainId) {
      domainGrants[adminUserId] = domainGrants[adminUserId].filter((item) => item.domain_id !== domainId);
      recordDomainGrantAudit(adminUserId, "admin_user.domain_grant_deleted", domainId);
      await route.fulfill({ status: 204 });
      return;
    }
    await route.fulfill({
      contentType: "application/json",
      json: domainGrants[adminUserId],
    });
  });
  await page.route(/http:\/\/localhost:8000\/admin\/users\/[^/]+\/status/, async (route) => {
    const adminUserId = new URL(route.request().url()).pathname.split("/")[3];
    const payload = route.request().postDataJSON() as { is_active: boolean };
    const target = adminUsers.find((user) => user.id === adminUserId);
    if (!target) {
      await route.fulfill({ contentType: "application/json", status: 404, json: { detail: "missing" } });
      return;
    }
    target.is_active = payload.is_active;
    target.updated_at = "2026-06-27T00:03:00Z";
    recordAdminAudit(target.id, "admin_user.status_updated", target.email);
    await route.fulfill({
      contentType: "application/json",
      json: target,
    });
  });
  await page.route(/http:\/\/localhost:8000\/admin\/users\/[^/]+\/roles/, async (route) => {
    const adminUserId = new URL(route.request().url()).pathname.split("/")[3];
    const payload = route.request().postDataJSON() as { roles: string[] };
    const target = adminUsers.find((user) => user.id === adminUserId);
    if (!target) {
      await route.fulfill({ contentType: "application/json", status: 404, json: { detail: "missing" } });
      return;
    }
    target.roles = payload.roles;
    target.updated_at = "2026-06-27T00:03:30Z";
    recordAdminAudit(target.id, "admin_user.roles_updated", target.email);
    await route.fulfill({
      contentType: "application/json",
      json: target,
    });
  });
  await page.route(/http:\/\/localhost:8000\/admin\/users\/[^/]+\/password/, async (route) => {
    const adminUserId = new URL(route.request().url()).pathname.split("/")[3];
    const target = adminUsers.find((user) => user.id === adminUserId);
    if (!target) {
      await route.fulfill({ contentType: "application/json", status: 404, json: { detail: "missing" } });
      return;
    }
    target.updated_at = "2026-06-27T00:04:00Z";
    recordAdminAudit(target.id, "admin_user.password_reset", target.email);
    await route.fulfill({
      contentType: "application/json",
      json: target,
    });
  });
  await page.route("http://localhost:8000/llm/providers", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: {
        active: {
          provider: "local",
          model: "ollama:gemma4",
          paid: false,
          can_call: true,
          reason: null,
        },
        agent_runtime: "deepagents",
        paid_providers_enabled: false,
        providers: [
          {
            name: "local",
            label: "Ollama local runtime",
            default_model: "gemma4",
            configured: true,
            enabled: true,
            paid: false,
            reason: null,
            missing_config: [],
            base_url: "http://ollama:11434/",
          },
          {
            name: "openai",
            label: "OpenAI",
            default_model: "gpt-5-mini",
            configured: false,
            enabled: false,
            paid: true,
            reason: "Missing required configuration",
            missing_config: ["RETOS_OPENAI_API_KEY"],
            base_url: null,
          },
        ],
      },
    });
  });
  await page.route("http://localhost:8000/llm/runtime-plan", async (route) => {
    const payload = route.request().postDataJSON() as {
      provider: string;
      agent_runtime: string;
      allow_paid_llm: boolean;
    };
    await route.fulfill({
      contentType: "application/json",
      json: {
        provider: payload.provider,
        model: payload.provider === "local" ? "ollama:gemma4" : "gpt-5-mini",
        agent_runtime: payload.agent_runtime,
        paid_provider: payload.provider !== "local",
        paid_providers_enabled: payload.allow_paid_llm,
        can_start: payload.provider === "local",
        restart_required: true,
        env: {
          RETOS_PROVIDER: payload.provider,
          RETOS_AGENT_RUNTIME: payload.agent_runtime,
          RETOS_MODEL: payload.provider === "local" ? "ollama:gemma4" : "gpt-5-mini",
          RETOS_ALLOW_PAID_LLM: String(payload.allow_paid_llm),
          RETOS_OLLAMA_MODEL: "gemma4",
          RETOS_OLLAMA_BASE_URL: "http://ollama:11434",
        },
        missing_config: [],
        warnings: ["Restart API and worker after changing runtime environment."],
        reason: null,
      },
    });
  });
  await page.route(/http:\/\/localhost:8000\/domains(?:\?.*)?$/, async (route) => {
    if (route.request().method() === "POST") {
      const created = {
        id: "domain-456",
        slug: "policy-research",
        name: "Policy Research",
        description: "Created from the console",
        archived_at: null,
        created_at: "2026-06-27T00:00:00Z",
        updated_at: "2026-06-27T00:00:00Z",
      };
      domains.push(created);
      await route.fulfill({
        contentType: "application/json",
        status: 201,
        json: created,
      });
      return;
    }

    const includeArchived = new URL(route.request().url()).searchParams.get("include_archived") === "true";
    await route.fulfill({
      contentType: "application/json",
      json: domains.filter((domain) => includeArchived || !domain.archived_at),
    });
  });
  await page.route(/http:\/\/localhost:8000\/domains\/[^/]+(?:\/restore)?$/, async (route) => {
    if (!["PATCH", "DELETE", "POST"].includes(route.request().method())) {
      await route.fallback();
      return;
    }
    const pathParts = new URL(route.request().url()).pathname.split("/");
    const domainId = pathParts[2];
    const index = domains.findIndex((domain) => domain.id === domainId);
    if (index === -1) {
      await route.fulfill({
        contentType: "application/json",
        status: 404,
        json: { detail: "Domain not found" },
      });
      return;
    }
    if (route.request().method() === "DELETE") {
      domains[index] = {
        ...domains[index],
        archived_at: "2026-06-27T00:06:00Z",
        updated_at: "2026-06-27T00:06:00Z",
      };
      journalEvents.unshift({
        id: `journal-domain-archived-${domainId}`,
        trace_id: null,
        occurred_at: "2026-06-27T00:06:00Z",
        actor: "admin@retos.dev",
        event_type: "domain.archived",
        entity_type: "domain",
        entity_id: domainId,
        payload: {
          domain_id: domainId,
          slug: domains[index].slug,
          archived_at: domains[index].archived_at,
          changes: [{ field: "archived_at", before: null, after: domains[index].archived_at }],
        },
      });
      await route.fulfill({
        contentType: "application/json",
        json: domains[index],
      });
      return;
    }
    if (route.request().method() === "POST" && pathParts[3] === "restore") {
      const before = domains[index].archived_at;
      domains[index] = {
        ...domains[index],
        archived_at: null,
        updated_at: "2026-06-27T00:07:00Z",
      };
      journalEvents.unshift({
        id: `journal-domain-restored-${domainId}`,
        trace_id: null,
        occurred_at: "2026-06-27T00:07:00Z",
        actor: "admin@retos.dev",
        event_type: "domain.restored",
        entity_type: "domain",
        entity_id: domainId,
        payload: {
          domain_id: domainId,
          slug: domains[index].slug,
          changes: [{ field: "archived_at", before, after: null }],
        },
      });
      await route.fulfill({
        contentType: "application/json",
        json: domains[index],
      });
      return;
    }
    const payload = route.request().postDataJSON() as {
      name: string;
      description: string | null;
    };
    domains[index] = {
      ...domains[index],
      name: payload.name,
      description: payload.description,
      updated_at: "2026-06-27T00:05:00Z",
    };
    await route.fulfill({
      contentType: "application/json",
      json: domains[index],
    });
  });
  await page.route(/http:\/\/localhost:8000\/domains\/[^/]+\/documents/, async (route) => {
    const domainId = new URL(route.request().url()).pathname.split("/")[2];
    const includeArchived = new URL(route.request().url()).searchParams.get("include_archived") === "true";
    await route.fulfill({
      contentType: "application/json",
      json: documents.filter(
        (document) => document.domain_id === domainId && (includeArchived || !document.archived_at),
      ),
    });
  });
  await page.route(/http:\/\/localhost:8000\/documents\/[^/]+\/restore$/, async (route) => {
    const documentId = new URL(route.request().url()).pathname.split("/")[2];
    const index = documents.findIndex((document) => document.id === documentId);
    if (index === -1) {
      await route.fulfill({
        contentType: "application/json",
        status: 404,
        json: { detail: "Document not found" },
      });
      return;
    }

    documents[index] = {
      ...documents[index],
      archived_at: null,
      updated_at: "2026-06-27T00:05:00Z",
    };
    journalEvents.unshift({
      id: `journal-document-restored-${documentId}`,
      trace_id: null,
      occurred_at: "2026-06-27T00:05:00Z",
      actor: "admin@retos.dev",
      event_type: "document.restored",
      entity_type: "document",
      entity_id: documentId,
      payload: {
        domain_id: documents[index].domain_id,
        changes: [{ field: "archived_at", before: "2026-06-27T00:04:00Z", after: null }],
      },
    });
    progressEvents.unshift({
      id: `progress-document-restored-${documentId}`,
      trace_id: null,
      job_id: null,
      occurred_at: "2026-06-27T00:05:00Z",
      event_type: "document.restored",
      message: `Restored document ${documents[index].title}`,
      payload: { document_id: documentId, domain_id: documents[index].domain_id },
    });
    await route.fulfill({
      contentType: "application/json",
      json: documents[index],
    });
  });
  await page.route(/http:\/\/localhost:8000\/documents\/[^/]+\/history$/, async (route) => {
    const documentId = new URL(route.request().url()).pathname.split("/")[2];
    const document = documents.find((item) => item.id === documentId);
    if (!document) {
      await route.fulfill({
        contentType: "application/json",
        status: 404,
        json: { detail: "Document not found" },
      });
      return;
    }
    await route.fulfill({
      contentType: "application/json",
      json: {
        document,
        events: journalEvents
          .filter((event) => event.entity_type === "document" && event.entity_id === documentId)
          .reverse()
          .map((event) => ({
            id: event.id,
            occurred_at: event.occurred_at,
            actor: event.actor,
            event_type: event.event_type,
            changes:
              event.event_type === "document.updated"
                ? [{ field: "title", before: "Uploaded Fixture", after: "Uploaded Fixture Reviewed" }]
                : event.event_type === "document.archived"
                  ? [{ field: "archived_at", before: null, after: "2026-06-27T00:04:00Z" }]
                  : event.event_type === "document.restored"
                    ? [{ field: "archived_at", before: "2026-06-27T00:04:00Z", after: null }]
                    : [],
            payload: event.payload,
          })),
      },
    });
  });
  await page.route(/http:\/\/localhost:8000\/documents\/[^/]+\/versions$/, async (route) => {
    const documentId = new URL(route.request().url()).pathname.split("/")[2];
    const document = documents.find((item) => item.id === documentId);
    if (!document) {
      await route.fulfill({
        contentType: "application/json",
        status: 404,
        json: { detail: "Document not found" },
      });
      return;
    }
    await route.fulfill({
      contentType: "application/json",
      json: documentVersions.filter((version) => version.document_id === documentId),
    });
  });
  await page.route(/http:\/\/localhost:8000\/document-versions\/[^/]+\/artifacts$/, async (route) => {
    const versionId = new URL(route.request().url()).pathname.split("/")[2];
    await route.fulfill({
      contentType: "application/json",
      json: artifacts.filter((artifact) => artifact.document_version_id === versionId),
    });
  });
  await page.route(/http:\/\/localhost:8000\/document-versions\/[^/]+\/segments$/, async (route) => {
    const versionId = new URL(route.request().url()).pathname.split("/")[2];
    await route.fulfill({
      contentType: "application/json",
      json: segments.filter((segment) => segment.document_version_id === versionId),
    });
  });
  await page.route(/http:\/\/localhost:8000\/documents\/[^/]+$/, async (route) => {
    const documentId = new URL(route.request().url()).pathname.split("/")[2];
    const index = documents.findIndex((document) => document.id === documentId);
    if (index === -1) {
      await route.fulfill({
        contentType: "application/json",
        status: 404,
        json: { detail: "Document not found" },
      });
      return;
    }

    if (route.request().method() === "PATCH") {
      const payload = (await route.request().postDataJSON()) as { title?: string };
      documents[index] = {
        ...documents[index],
        title: payload.title ?? documents[index].title,
        updated_at: "2026-06-27T00:03:00Z",
      };
      journalEvents.unshift({
        id: `journal-document-updated-${documentId}`,
        trace_id: null,
        occurred_at: "2026-06-27T00:03:00Z",
        actor: "admin@retos.dev",
        event_type: "document.updated",
        entity_type: "document",
        entity_id: documentId,
        payload: {
          domain_id: documents[index].domain_id,
          title_changed: true,
          changes: [{ field: "title", before: "Uploaded Fixture", after: documents[index].title }],
        },
      });
      progressEvents.unshift({
        id: `progress-document-updated-${documentId}`,
        trace_id: null,
        job_id: null,
        occurred_at: "2026-06-27T00:03:00Z",
        event_type: "document.updated",
        message: `Updated document ${documents[index].title}`,
        payload: { document_id: documentId, domain_id: documents[index].domain_id },
      });
      await route.fulfill({
        contentType: "application/json",
        json: documents[index],
      });
      return;
    }

    if (route.request().method() === "DELETE") {
      documents[index] = {
        ...documents[index],
        archived_at: "2026-06-27T00:04:00Z",
        updated_at: "2026-06-27T00:04:00Z",
      };
      journalEvents.unshift({
        id: `journal-document-archived-${documentId}`,
        trace_id: null,
        occurred_at: "2026-06-27T00:04:00Z",
        actor: "admin@retos.dev",
        event_type: "document.archived",
        entity_type: "document",
        entity_id: documentId,
        payload: {
          domain_id: documents[index].domain_id,
          changes: [{ field: "archived_at", before: null, after: "2026-06-27T00:04:00Z" }],
        },
      });
      progressEvents.unshift({
        id: `progress-document-archived-${documentId}`,
        trace_id: null,
        job_id: null,
        occurred_at: "2026-06-27T00:04:00Z",
        event_type: "document.archived",
        message: `Archived document ${documents[index].title}`,
        payload: { document_id: documentId, domain_id: documents[index].domain_id },
      });
      await route.fulfill({
        contentType: "application/json",
        json: documents[index],
      });
      return;
    }

    await route.fulfill({
      contentType: "application/json",
      json: documents[index],
    });
  });
  await page.route(/http:\/\/localhost:8000\/jobs\?limit=\d+/, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: jobs,
    });
  });
  await page.route(/http:\/\/localhost:8000\/jobs\/[^/?]+$/, async (route) => {
    const jobId = new URL(route.request().url()).pathname.split("/")[2];
    const job = jobs.find((item) => item.id === jobId);
    if (!job) {
      await route.fulfill({
        contentType: "application/json",
        status: 404,
        json: { detail: "Job not found" },
      });
      return;
    }
    await route.fulfill({
      contentType: "application/json",
      json: job,
    });
  });
  await page.route(/http:\/\/localhost:8000\/jobs\/[^/]+\/retry$/, async (route) => {
    const jobId = new URL(route.request().url()).pathname.split("/")[2];
    const original = jobs.find((item) => item.id === jobId);
    if (!original || !["failed", "cancelled"].includes(original.status)) {
      await route.fulfill({
        contentType: "application/json",
        status: 409,
        json: { detail: "Cannot retry job from queued" },
      });
      return;
    }
    const retried = jobFixture(`job-retry-${jobId}`, original.kind, "queued", {
      ...original.payload,
      retried_from_job_id: original.id,
      retry_requested_at: "2026-06-27T00:06:00Z",
    });
    jobs.unshift(retried);
    recordAudit(retried);
    await route.fulfill({
      contentType: "application/json",
      status: 202,
      json: retried,
    });
  });
  await page.route(/http:\/\/localhost:8000\/audit\/journal-events\?limit=\d+/, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: journalEvents,
    });
  });
  await page.route(/http:\/\/localhost:8000\/audit\/progress-events\?limit=\d+/, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: progressEvents,
    });
  });
  await page.route(/http:\/\/localhost:8000\/audit\/export\?limit=\d+/, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      headers: {
        "content-disposition": 'attachment; filename="retos-audit-export.json"',
        "cache-control": "no-store",
      },
      json: {
        schema_version: "retos.audit-export.v2",
        generated_at: "2026-06-27T00:02:00Z",
        limit: 200,
        journal_events: journalEvents,
        progress_events: progressEvents,
        integrity: {
          algorithm: "sha256",
          canonicalization: "json-sort-keys-v1",
          valid: true,
          event_count: journalEvents.length + progressEvents.length,
          head_hash: "hash-final",
          failures: [],
          continuity_gaps: [],
          chain: [
            {
              event_id: "journal-event-1",
              trace_id: "job-seed-1",
              event_stream: "journal",
              event_type: "job.created",
              occurred_at: "2026-06-27T00:00:00Z",
              payload_hash: auditHashFields.payload_hash,
              prev_hash: null,
              event_hash: auditHashFields.event_hash,
            },
          ],
        },
      },
    });
  });
  await page.route(/http:\/\/localhost:8000\/domains\/[^/]+\/sources/, async (route) => {
    const pathParts = new URL(route.request().url()).pathname.split("/");
    const domainId = pathParts[2];
    const sourceId = pathParts[4] ?? null;
    if (route.request().method() === "PATCH" && sourceId) {
      const payload = (await route.request().postDataJSON()) as {
        kind: "mount" | "upload" | "url";
        name: string;
        uri: string;
      };
      const index = sources.findIndex(
        (source) => source.domain_id === domainId && source.id === sourceId,
      );
      if (index === -1) {
        await route.fulfill({
          contentType: "application/json",
          status: 404,
          json: { detail: "Source not found" },
        });
        return;
      }
      const updated = {
        ...sources[index],
        kind: payload.kind,
        name: payload.name,
        uri: payload.uri,
        updated_at: "2026-06-27T00:02:00Z",
      };
      sources[index] = updated;
      await route.fulfill({
        contentType: "application/json",
        json: updated,
      });
      return;
    }
    if (route.request().method() === "DELETE" && sourceId) {
      const index = sources.findIndex(
        (source) => source.domain_id === domainId && source.id === sourceId,
      );
      if (index === -1) {
        await route.fulfill({
          contentType: "application/json",
          status: 404,
          json: { detail: "Source not found" },
        });
        return;
      }
      const [deleted] = sources.splice(index, 1);
      for (const document of documents) {
        if (document.source_id === sourceId) {
          document.source_id = null;
        }
      }
      journalEvents.unshift({
        id: `journal-source-deleted-${sourceId}`,
        trace_id: null,
        occurred_at: "2026-06-27T00:02:30Z",
        actor: "admin@retos.dev",
        event_type: "source.deleted",
        entity_type: "source",
        entity_id: sourceId,
        payload: {
          domain_id: domainId,
          source_id: deleted.id,
          kind: deleted.kind,
          name: deleted.name,
          uri: deleted.uri,
        },
      });
      await route.fulfill({
        contentType: "application/json",
        json: deleted,
      });
      return;
    }
    if (route.request().method() === "POST") {
      const created = {
        id: "source-456",
        domain_id: domainId,
        kind: "mount",
        name: "Policy Corpus",
        uri: "file:///corpus/policy",
        created_at: "2026-06-27T00:00:00Z",
        updated_at: "2026-06-27T00:00:00Z",
      };
      sources.push(created);
      await route.fulfill({
        contentType: "application/json",
        status: 201,
        json: created,
      });
      return;
    }

    await route.fulfill({
      contentType: "application/json",
      json: sources.filter((source) => source.domain_id === domainId),
    });
  });
  await page.route(/http:\/\/localhost:8000\/sources\/[^/]+\/scan/, async (route) => {
    const job = jobFixture("job-scan-1", "ingest.source", "queued", { ingestion_kind: "source_scan" });
    jobs.unshift(job);
    recordAudit(job);
    await route.fulfill({
      contentType: "application/json",
      status: 202,
      json: job,
    });
  });
  await page.route(/http:\/\/localhost:8000\/domains\/[^/]+\/index\/rebuild/, async (route) => {
    const job = jobFixture("job-index-1", "index.domain", "queued", { requested_at: "now" });
    jobs.unshift(job);
    recordAudit(job);
    await route.fulfill({
      contentType: "application/json",
      status: 202,
      json: job,
    });
  });
  await page.route(/http:\/\/localhost:8000\/domains\/[^/]+\/ingestions\/text/, async (route) => {
    const domainId = new URL(route.request().url()).pathname.split("/")[2];
    documents.push({
      id: "document-2",
      domain_id: domainId,
      source_id: null,
      external_id: "inline-note",
      title: "Policy Note",
      content_hash: "fedcba9876543210",
      metadata: {},
      source_uri: "inline://policy-research/policy-note",
      size_bytes: 256,
      archived_at: null,
      created_at: "2026-06-27T00:00:00Z",
      updated_at: "2026-06-27T00:00:00Z",
    });
    const job = jobFixture("job-text-1", "ingest.source", "queued", { title: "Policy Note" });
    jobs.unshift(job);
    recordAudit(job);
    await route.fulfill({
      contentType: "application/json",
      status: 202,
      json: job,
    });
  });
  await page.route(/http:\/\/localhost:8000\/domains\/[^/]+\/ingestions\/upload/, async (route) => {
    const domainId = new URL(route.request().url()).pathname.split("/")[2];
    if ((route.request().postData() ?? "").includes("Rejected Fixture")) {
      await route.fulfill({
        contentType: "application/json",
        status: 400,
        json: { detail: "Only .txt, .md, and .pdf files can be uploaded" },
      });
      return;
    }
    documents.push({
      id: "document-upload-1",
      domain_id: domainId,
      source_id: null,
      external_id: "uploaded-fixture.txt",
      title: "Uploaded Fixture",
      content_hash: "1234567890abcdef",
      metadata: { ingestion: { kind: "file_upload" } },
      source_uri: "storage://uploads/domain-456/uploaded-fixture.txt",
      size_bytes: 512,
      archived_at: null,
      created_at: "2026-06-27T00:00:00Z",
      updated_at: "2026-06-27T00:00:00Z",
    });
    const job = jobFixture("job-upload-1", "ingest.source", "succeeded", {
      ingestion_kind: "file_upload",
      filename: "uploaded-fixture.txt",
    });
    jobs.unshift(job);
    recordAudit(job);
    await route.fulfill({
      contentType: "application/json",
      status: 202,
      json: job,
    });
  });
  await page.route(/http:\/\/localhost:8000\/domains\/[^/]+\/queries/, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: {
        job: {
          ...jobFixture("job-query-1", "agent.query", "succeeded"),
        },
        result: {
          answer:
            "Grounded answer for: What evidence mentions search readiness?\n\nThe indexed evidence points to: Smoke segment text for search readiness.",
          provider: "local",
          model: "ollama:gemma4",
          runtime: "deterministic",
          evidence_audit: {
            grounded: true,
            cited_segment_ids: ["segment-1234567890"],
            unreferenced_citation_ids: [],
          },
          contradiction_audit: {
            checked: true,
            conflict_count: 0,
            findings: [],
          },
          multi_hop_audit: {
            checked: true,
            requires_multi_hop: true,
            status: "supported_multi_document",
            document_count: 2,
            bridge_terms: ["search", "readiness"],
            warnings: [],
          },
          query_plan: {
            strategy: "multi_hop_evidence_route",
            requires_multi_hop: true,
            search_queries: [
              "What evidence mentions search readiness?",
              "evidence mentions readiness search",
            ],
            expected_evidence: "multi_document",
            warnings: [],
            steps: [
              {
                name: "search",
                description: "Run bounded BM25 search over the selected domain.",
                status: "planned",
              },
              {
                name: "read",
                description: "Read only citations returned by controlled corpus search.",
                status: "planned",
              },
            ],
          },
          evidence_route: {
            coverage_level: "single_segment",
            segment_count: 1,
            document_count: 1,
            anchor_count: 1,
            multi_document: false,
            has_neighbor_context: true,
            warnings: ["single_citation", "single_document"],
            documents: [
              {
                document_id: "document-1",
                title: "Smoke Document",
                segment_ids: ["segment-1234567890"],
                anchors: ["page=1"],
              },
            ],
          },
          usage: {
            budget: {
              max_searches: 8,
              max_citations: 5,
              max_evidence_tokens: 16000,
              max_runtime_seconds: 120,
            },
            search_count: 1,
            citation_count: 1,
            evidence_tokens: 6,
            runtime_ms: 24,
            within_budget: true,
          },
          citations: [
            {
              segment_id: "segment-1234567890",
              document_id: "document-1",
              document_version_id: "version-1",
              title: "Smoke Document",
              anchor: "page=1",
              score: 1.23,
              text: "Smoke segment text for search readiness.",
            },
          ],
          neighbor_context: [
            {
              segment_id: "segment-neighbor-1",
              source_segment_id: "segment-1234567890",
              document_id: "document-1",
              document_version_id: "version-1",
              title: "Smoke Document",
              anchor: "page=2",
              ordinal: 2,
              distance: 1,
              text: "Adjacent context explains who reviewed the search readiness evidence.",
              token_count: 9,
            },
          ],
        },
      },
    });
  });
  await page.route("http://localhost:8000/evals/smoke", async (route) => {
    const job = jobFixture("job-eval-1", "eval.run", "succeeded", { result: evalReport }, null);
    jobs.unshift(job);
    evalRuns.unshift({ job, report: evalReport });
    recordAudit(job);
    await route.fulfill({
      contentType: "application/json",
      status: 202,
      json: { job, report: evalReport },
    });
  });
  await page.route("http://localhost:8000/evals/agent-multihop", async (route) => {
    const job = jobFixture(
      "job-eval-agent-multihop-1",
      "eval.run",
      "succeeded",
      {
        result: agentMultihopReport,
      },
      null,
    );
    jobs.unshift(job);
    evalRuns.unshift({ job, report: agentMultihopReport });
    recordAudit(job);
    await route.fulfill({
      contentType: "application/json",
      status: 202,
      json: { job, report: agentMultihopReport },
    });
  });
  await page.route("http://localhost:8000/evals/squad", async (route) => {
    const payload = route.request().postDataJSON() as Record<string, unknown>;
    expect(payload.domain_id).toBe("domain-123");
    const domainId = typeof payload.domain_id === "string" ? payload.domain_id : null;
    const reportPaths = {
      json: "/var/lib/retos/evals/reports/ui-squad.json",
      markdown: "/var/lib/retos/evals/reports/ui-squad.md",
    };
    const job = jobFixture(
      "job-eval-squad-1",
      "eval.run",
      "succeeded",
      {
        dataset_path: "/var/lib/retos/evals/datasets/ui-squad.json",
        max_cases: 2,
        domain_id: payload.domain_id ?? null,
        report_paths: reportPaths,
        result: squadReport,
      },
      domainId,
    );
    jobs.unshift(job);
    evalRuns.unshift({ job, report: squadReport });
    recordAudit(job);
    await route.fulfill({
      contentType: "application/json",
      status: 202,
      json: { job, report: squadReport, report_paths: reportPaths },
    });
  });
  await page.route("http://localhost:8000/evals/hotpotqa", async (route) => {
    const payload = route.request().postDataJSON() as Record<string, unknown>;
    const domainId = typeof payload.domain_id === "string" ? payload.domain_id : null;
    const reportPaths = {
      json: "/var/lib/retos/evals/reports/ui-hotpotqa.json",
      markdown: "/var/lib/retos/evals/reports/ui-hotpotqa.md",
    };
    const job = jobFixture(
      "job-eval-hotpotqa-1",
      "eval.run",
      "succeeded",
      {
        dataset_path: "/var/lib/retos/evals/datasets/ui-hotpotqa.json",
        max_cases: 1,
        domain_id: payload.domain_id ?? null,
        report_paths: reportPaths,
        result: hotpotqaReport,
      },
      domainId,
    );
    jobs.unshift(job);
    evalRuns.unshift({ job, report: hotpotqaReport });
    recordAudit(job);
    await route.fulfill({
      contentType: "application/json",
      status: 202,
      json: { job, report: hotpotqaReport, report_paths: reportPaths },
    });
  });
  await page.route("http://localhost:8000/evals/hotpotqa-agent", async (route) => {
    const payload = route.request().postDataJSON() as Record<string, unknown>;
    expect(payload.domain_id).toBe("domain-123");
    const domainId = typeof payload.domain_id === "string" ? payload.domain_id : null;
    const reportPaths = {
      json: "/var/lib/retos/evals/reports/ui-hotpotqa-agent.json",
      markdown: "/var/lib/retos/evals/reports/ui-hotpotqa-agent.md",
    };
    const job = jobFixture(
      "job-eval-hotpotqa-agent-1",
      "eval.run",
      "succeeded",
      {
        dataset_path: "/var/lib/retos/evals/datasets/ui-hotpotqa.json",
        max_cases: 1,
        domain_id: payload.domain_id ?? null,
        report_paths: reportPaths,
        result: hotpotqaAgentReport,
      },
      domainId,
    );
    jobs.unshift(job);
    evalRuns.unshift({ job, report: hotpotqaAgentReport });
    recordAudit(job);
    await route.fulfill({
      contentType: "application/json",
      status: 202,
      json: { job, report: hotpotqaAgentReport, report_paths: reportPaths },
    });
  });
  await page.route("http://localhost:8000/evals/natural-questions", async (route) => {
    const payload = route.request().postDataJSON() as Record<string, unknown>;
    const domainId = typeof payload.domain_id === "string" ? payload.domain_id : null;
    const reportPaths = {
      json: "/var/lib/retos/evals/reports/ui-natural-questions.json",
      markdown: "/var/lib/retos/evals/reports/ui-natural-questions.md",
    };
    const job = jobFixture(
      "job-eval-natural-questions-1",
      "eval.run",
      "succeeded",
      {
        dataset_path: "/var/lib/retos/evals/datasets/ui-nq.jsonl",
        max_cases: 1,
        domain_id: payload.domain_id ?? null,
        report_paths: reportPaths,
        result: naturalQuestionsReport,
      },
      domainId,
    );
    jobs.unshift(job);
    evalRuns.unshift({ job, report: naturalQuestionsReport });
    recordAudit(job);
    await route.fulfill({
      contentType: "application/json",
      status: 202,
      json: { job, report: naturalQuestionsReport, report_paths: reportPaths },
    });
  });
  await page.route("http://localhost:8000/evals/ocr-benchmark", async (route) => {
    const payload = route.request().postDataJSON() as {
      dataset_path: string;
      dataset_format: string;
      max_cases: number;
      domain_id?: string | null;
    };
    const domainId = typeof payload.domain_id === "string" ? payload.domain_id : null;
    const reportPaths = {
      json: "/var/lib/retos/evals/reports/ui-ocr-benchmark.json",
      markdown: "/var/lib/retos/evals/reports/ui-ocr-benchmark.md",
    };
    const job = jobFixture(
      "job-eval-ocr-benchmark-1",
      "eval.run",
      "succeeded",
      {
        dataset_path: `/var/lib/retos/evals/datasets/${payload.dataset_path}`,
        dataset_format: payload.dataset_format,
        max_cases: payload.max_cases,
        domain_id: payload.domain_id ?? null,
        report_paths: reportPaths,
        result: ocrBenchmarkReport,
      },
      domainId,
    );
    jobs.unshift(job);
    evalRuns.unshift({ job, report: ocrBenchmarkReport });
    recordAudit(job);
    await route.fulfill({
      contentType: "application/json",
      status: 202,
      json: { job, report: ocrBenchmarkReport, report_paths: reportPaths },
    });
  });
  await page.route(/http:\/\/localhost:8000\/evals\/runs\?.*/, async (route) => {
    const runs = evalRunsForRequestUrl(route.request().url());
    await route.fulfill({
      contentType: "application/json",
      json: runs,
    });
  });
  await page.route(/http:\/\/localhost:8000\/evals\/runs\/trends\?.*/, async (route) => {
    const runs = evalRunsForRequestUrl(route.request().url());
    await route.fulfill({
      contentType: "application/json",
      json: buildEvalTrends(runs),
    });
  });
  await page.route(/http:\/\/localhost:8000\/evals\/runs\/([^/]+)\/rerun/, async (route) => {
    const match = route.request().url().match(/\/evals\/runs\/([^/]+)\/rerun$/);
    const originalJobId = match ? decodeURIComponent(match[1]) : "";
    const original = evalRuns.find((run) => run.job.id === originalJobId);
    if (!original) {
      await route.fulfill({
        contentType: "application/json",
        status: 404,
        json: { detail: "Eval run not found" },
      });
      return;
    }
    evalRerunCount += 1;
    const reportPaths = original.job.payload.report_paths ?? null;
    const job = jobFixture(
      `job-eval-rerun-${evalRerunCount}`,
      "eval.run",
      "succeeded",
      {
        ...original.job.payload,
        rerun_from_job_id: original.job.id,
      },
      original.job.domain_id,
    );
    jobs.unshift(job);
    evalRuns.unshift({ job, report: original.report });
    recordAudit(job);
    await route.fulfill({
      contentType: "application/json",
      status: 202,
      json: { job, report: original.report, report_paths: reportPaths },
    });
  });
  await page.route(/http:\/\/localhost:8000\/evals\/runs\/compare.*/, async (route) => {
    expect(new URL(route.request().url()).searchParams.get("domain_id")).toBe("domain-123");
    await route.fulfill({
      contentType: "application/json",
      json: evalComparison,
    });
  });
  await page.route(/http:\/\/localhost:8000\/evals\/runs\/regression-gate.*/, async (route) => {
    expect(new URL(route.request().url()).searchParams.get("domain_id")).toBe("domain-123");
    await route.fulfill({
      contentType: "application/json",
      json: evalRegressionGate,
    });
  });
  await page.route("http://localhost:8000/events/progress", async (route) => {
    await route.fulfill({
      contentType: "text/event-stream",
      body: [
        "id: progress:progress-seed-1",
        "event: job.queued",
        'data: {"id":"progress:progress-seed-1","event":"job.queued","data":{"job_id":"job-seed-1","status":"queued","occurred_at":"2026-06-27T00:00:00Z","message":"Persisted progress replayed"}}',
        "",
        "id: live:2",
        "event: agent.started",
        'data: {"id":"live:2","event":"agent.started","data":{"job_id":"job-query-1","status":"running","message":"Agent query started"}}',
        "",
        "",
      ].join("\n"),
    });
  });
}

test.beforeEach(async ({ page }) => {
  await mockProviderApi(page);
  await page.goto("/");
});

test("keeps the RetOS brand system accessible and responsive", async ({ page }) => {
  await expect(page).toHaveTitle("RetOS");
  await expect(page.locator('meta[name="theme-color"]')).toHaveAttribute("content", "#0f172a");
  await expect(page.locator('link[rel="icon"]')).toHaveAttribute("href", "/retos-mark.svg");

  const brandMark = page.locator(".brand img");
  await expect(brandMark).toHaveAttribute("src", "/retos-mark.svg");
  await expect(page.locator(".brand")).toContainText("RetOS");
  await expect(page.locator(".brand")).toContainText("Audit console");

  await expect(page.locator(".brand-brief")).toContainText("Docker-first runtime");
  await expect(page.locator(".brand-brief")).toContainText("Revision abcdef123456");
  await expect(page.locator(".brand-brief")).toContainText("API ready: database ok");
  await expect(page.locator(".brand-brief")).toContainText("Hash-chained journals");
  await expect(page.locator(".brand-brief")).toContainText("No paid calls in tests");
  await expect(page.getByLabel("System metrics").getByText("Build")).toBeVisible();
  await expect(page.getByLabel("System metrics").getByText("2026.06.29-local")).toBeVisible();

  const theme = await page.evaluate(() => {
    const root = getComputedStyle(document.documentElement);
    const sidebar = getComputedStyle(document.querySelector(".sidebar") as HTMLElement);
    const primaryAction = getComputedStyle(document.querySelector(".primary-action") as HTMLElement);
    const panel = getComputedStyle(document.querySelector(".panel") as HTMLElement);
    return {
      ink: root.getPropertyValue("--retos-ink").trim(),
      primary: root.getPropertyValue("--retos-primary").trim(),
      action: root.getPropertyValue("--retos-action").trim(),
      canvas: root.getPropertyValue("--retos-canvas").trim(),
      sidebarBackground: sidebar.backgroundColor,
      actionBackground: primaryAction.backgroundColor,
      panelRadius: panel.borderRadius,
    };
  });

  expect(theme).toEqual({
    ink: "#0f172a",
    primary: "#2563eb",
    action: "#f97316",
    canvas: "#f8fafc",
    sidebarBackground: "rgb(15, 23, 42)",
    actionBackground: "rgb(249, 115, 22)",
    panelRadius: "8px",
  });

  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to workspace" })).toBeFocused();

  await page.emulateMedia({ reducedMotion: "reduce" });
  const transitionDurationMs = await page.locator(".primary-action").evaluate((element) => {
    const duration = getComputedStyle(element).transitionDuration;
    return duration.endsWith("ms") ? Number.parseFloat(duration) : Number.parseFloat(duration) * 1000;
  });
  expect(transitionDurationMs).toBeLessThanOrEqual(0.01);

  for (const width of [375, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    const hasHorizontalOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    );
    expect(hasHorizontalOverflow).toBe(false);
  }

  if (process.env.RETOS_VISUAL_AUDIT === "1") {
    await mkdir(VISUAL_AUDIT_DIR, { recursive: true });
    await page.locator("#overview").focus();
    const desktopViewport = { width: 1440, height: 900 };
    const mobileViewport = { width: 390, height: 844 };
    const desktopPath = resolve(VISUAL_AUDIT_DIR, "retos-console-desktop.png");
    const mobilePath = resolve(VISUAL_AUDIT_DIR, "retos-console-mobile.png");

    await page.setViewportSize(desktopViewport);
    await page.screenshot({
      fullPage: true,
      path: desktopPath,
    });
    await page.setViewportSize(mobileViewport);
    await page.screenshot({
      fullPage: true,
      path: mobilePath,
    });
    await writeFile(
      resolve(VISUAL_AUDIT_DIR, "manifest.json"),
      `${JSON.stringify(
        {
          generated_by: "frontend/e2e/app.spec.ts",
          screenshots: [
            await visualAuditRecord("desktop", desktopPath, desktopViewport),
            await visualAuditRecord("mobile", mobilePath, mobileViewport),
          ],
        },
        null,
        2,
      )}\n`,
      "utf8",
    );
  }
});

test("keeps operational modules compact and segmented", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });

  const modules: Array<[string, string | null]> = [
    ["overview", null],
    ["documents", "documents-library"],
    ["documents", "documents-sources"],
    ["documents", "documents-upload"],
    ["documents", "documents-text"],
    ["queries", "queries-runner"],
    ["queries", "queries-live"],
    ["evals", "evals-runner"],
    ["evals", "evals-results"],
    ["evals", "evals-history"],
    ["audit", "audit-jobs"],
    ["audit", "audit-progress"],
    ["audit", "audit-events"],
    ["admin", "admin-providers"],
    ["admin", "admin-users"],
  ];
  const sectionLabels = new Map([
    ["overview", "Overview"],
    ["documents", "Documents"],
    ["queries", "Queries"],
    ["evals", "Evals"],
    ["audit", "Audit"],
    ["admin", "Admin"],
  ]);

  for (const [section, module] of modules) {
    await page
      .getByLabel("Primary navigation")
      .getByRole("link", { name: sectionLabels.get(section) ?? section })
      .click();
    if (module) {
      await page.locator(`.module-nav a[href="#${module}"]`).click();
    }

    const layout = await page.evaluate(
      ({ section, module }) => {
        const panel =
          section === "overview"
            ? document.querySelector(".overview-layout")
            : document.querySelector(`#${section}`);
        const active = module
          ? document.querySelector(`#${module}`)
          : document.querySelector(".overview-layout");
        const workspace = document.querySelector(".workspace");
        return {
          activeHeight: Math.round(active?.getBoundingClientRect().height ?? 0),
          activeScroll: active ? active.scrollHeight - active.clientHeight : 0,
          bodyHorizontalOverflow:
            document.documentElement.scrollWidth > document.documentElement.clientWidth,
          panelScroll: panel ? panel.scrollHeight - panel.clientHeight : 0,
          tooltipTargets: [
            ...document.querySelectorAll(".workspace [data-tooltip], .sidebar [data-tooltip]"),
          ].filter((element) => element.getClientRects().length > 0).length,
          workspaceScroll: workspace ? workspace.scrollHeight - workspace.clientHeight : 0,
        };
      },
      { section, module },
    );

    expect(layout.bodyHorizontalOverflow, `${section}/${module ?? "overview"} horizontal overflow`).toBe(
      false,
    );
    expect(layout.workspaceScroll, `${section}/${module ?? "overview"} workspace scroll`).toBeLessThanOrEqual(
      0,
    );
    expect(layout.activeHeight, `${section}/${module ?? "overview"} active height`).toBeLessThanOrEqual(
      650,
    );
    expect(layout.panelScroll, `${section}/${module ?? "overview"} panel scroll`).toBeLessThanOrEqual(
      section === "documents" && module === "documents-library" ? 140 : 20,
    );
    expect(layout.activeScroll, `${section}/${module ?? "overview"} active scroll`).toBeLessThanOrEqual(
      section === "documents" && module === "documents-library" ? 140 : 20,
    );
    expect(layout.tooltipTargets, `${section}/${module ?? "overview"} tooltip targets`).toBeGreaterThan(0);
  }
});

test("seeds the local demo corpus from the overview", async ({ page }) => {
  await page.locator(".workflow-button").click();

  await expect(page).toHaveURL(/#documents-library$/);
  await expect(page.getByLabel("Active domain")).toHaveValue("domain-demo");
  await expect(page.locator("#documents").getByText("retos-demo", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Domain documents").getByText("Apollo Guidance Notes")).toBeVisible();
  await expect(page.getByRole("status").getByText("Demo corpus ready: 2 created, 0 skipped.")).toBeVisible();
});

test("clears expired stored admin sessions", async ({ page }) => {
  await page.evaluate(() => localStorage.setItem("retos.adminToken", "expired-token"));
  await page.route("http://localhost:8000/llm/providers", async (route) => {
    expect(route.request().headers().authorization).toBe("Bearer expired-token");
    await route.fulfill({
      contentType: "application/json",
      status: 401,
      json: { detail: "Token has expired" },
    });
  });
  await page.reload();

  await page.getByRole("link", { name: "Admin" }).first().click();
  await expect(page.getByLabel("Password", { exact: true })).toHaveValue("stored-session");
  await page.getByRole("button", { name: "Load providers" }).click();

  await expect(page.getByRole("alert")).toContainText(
    "Admin session expired. Enter the password and reconnect.",
  );
  await expect(page.getByLabel("Password", { exact: true })).toBeEditable();
  await expect(page.getByLabel("Password", { exact: true })).toHaveValue("");
  await expect(page.getByText("Connect admin session")).toBeVisible();
  const storedToken = await page.evaluate(() => localStorage.getItem("retos.adminToken"));
  expect(storedToken).toBeNull();
});

test("clears expired stored admin sessions from workspace refresh", async ({ page }) => {
  await page.evaluate(() => localStorage.setItem("retos.adminToken", "expired-token"));
  await page.unroute(/http:\/\/localhost:8000\/domains(?:\?.*)?$/);
  await page.route(/http:\/\/localhost:8000\/domains(?:\?.*)?$/, async (route) => {
    expect(route.request().headers().authorization).toBe("Bearer expired-token");
    await route.fulfill({
      contentType: "application/json",
      status: 401,
      json: { detail: "Token has expired" },
    });
  });
  await page.reload();

  await page.getByRole("button", { name: "Refresh workspace" }).click();

  await expect(page.getByRole("alert")).toContainText(
    "Admin session expired. Enter the password and reconnect.",
  );
  const storedToken = await page.evaluate(() => localStorage.getItem("retos.adminToken"));
  expect(storedToken).toBeNull();
  await page.getByRole("link", { name: "Admin" }).first().click();
  await expect(page.getByText("Connect admin session")).toBeVisible();
});

test("loads the operational console", async ({ page }) => {
  test.setTimeout(45_000);

  await expect(
    page.getByRole("heading", { name: "Auditable document investigation" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Refresh workspace" })).toBeVisible();
  const primaryNavigation = page.getByLabel("Primary navigation");
  await expect(primaryNavigation.getByRole("link", { name: "Documents" })).toBeVisible();
  await expect(primaryNavigation.getByRole("link", { name: "Documents" })).toHaveAttribute(
    "data-tooltip",
    /Manage domains/,
  );
  await expect(page.getByRole("link", { name: "Grounded query workflow" })).toBeVisible();

  await page.getByRole("link", { name: "Admin" }).first().click();
  await expect(page.locator("#admin").getByRole("heading", { name: "LLM providers" })).toBeVisible();
  const workspaceContext = page.getByLabel("Current workspace context");
  await expect(workspaceContext.getByText("Admin", { exact: true })).toBeVisible();
  await expect(workspaceContext.getByText("Providers", { exact: true })).toBeVisible();
  await expect(workspaceContext.getByText("1 of 2")).toHaveAttribute(
    "data-tooltip",
    /module position/,
  );
  await expect(page.getByLabel("Admin modules").getByRole("link", { name: "Providers" })).toHaveAttribute(
    "data-tooltip",
    /provider readiness/,
  );
  const chromeTooltipPlacement = await page.locator(".module-nav a[href='#admin-providers']").evaluate((element) => {
    const tooltipStyle = getComputedStyle(element, "::after");
    return {
      bottom: tooltipStyle.bottom,
      top: tooltipStyle.top,
    };
  });
  expect(chromeTooltipPlacement.top).not.toBe("auto");
  expect(chromeTooltipPlacement.bottom).toBe("auto");
  await expect(page.getByLabel("Admin modules").getByRole("link", { name: "Users" })).toHaveAttribute(
    "href",
    "#admin-users",
  );
  await page.getByLabel("Admin modules").getByRole("link", { name: "Users" }).click();
  await expect(workspaceContext.getByText("Users", { exact: true })).toBeVisible();
  await expect(workspaceContext.getByText("2 of 2")).toBeVisible();
  await page.getByLabel("Admin modules").getByRole("link", { name: "Providers" }).click();

  await page.getByLabel("Password", { exact: true }).fill("retos-dev-admin-change-me");
  await page.getByRole("button", { name: "Load providers" }).click();

  await expect(page.getByText("Active provider")).toBeVisible();
  await expect(page.getByText("Active model")).toBeVisible();
  await expect(page.getByLabel("Provider runtime context").getByText("Ollama", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Provider runtime context").getByText("deepagents")).toBeVisible();
  await expect(
    page.getByLabel("Provider runtime context").locator("[data-tooltip]").filter({
      hasText: "Paid providers blocked",
    }),
  ).toHaveAttribute("data-tooltip", /explicit configuration/);
  await expect(page.locator(".provider-summary").getByText("Agent runtime")).toBeVisible();
  await expect(page.getByText("ollama:gemma4")).toBeVisible();
  await expect(page.locator(".provider-summary").getByText("deepagents")).toBeVisible();
  await expect(page.locator(".provider-summary").getByText("Paid providers blocked")).toBeVisible();
  await expect(page.getByLabel("Runtime switch planner")).toBeVisible();
  await page.getByLabel("Runtime plan provider").selectOption("local");
  await page.getByLabel("Runtime plan agent runtime").selectOption("deepagents");
  await page.getByRole("button", { name: "Preview plan" }).click();
  await expect(page.getByLabel("Runtime environment plan").getByText("Can start after restart")).toBeVisible();
  await expect(page.getByLabel("Runtime environment plan").getByText("RETOS_AGENT_RUNTIME")).toBeVisible();
  await expect(page.getByLabel("Runtime environment plan").getByText("deepagents")).toBeVisible();
  const localProviderRow = page
    .getByLabel("Available LLM providers")
    .locator(".provider-row")
    .filter({ hasText: "Ollama local runtime" });
  await expect(localProviderRow.getByText("Active")).toBeVisible();
  await expect(localProviderRow.getByText("Configured")).toBeVisible();
  await expect(localProviderRow.getByText("Enabled")).toBeVisible();
  const openAiProviderRow = page
    .getByLabel("Available LLM providers")
    .locator(".provider-row")
    .filter({ hasText: "OpenAI" });
  await expect(openAiProviderRow.getByText("Available")).toBeVisible();
  await expect(openAiProviderRow.getByText("Missing config")).toBeVisible();
  await expect(openAiProviderRow.getByText("Blocked")).toBeVisible();
  await expect(openAiProviderRow.getByText("Missing RETOS_OPENAI_API_KEY")).toBeVisible();
  await page.getByLabel("Admin modules").getByRole("link", { name: "Users" }).click();
  await expect(page.getByLabel("Admin users context").getByText("Active users")).toBeVisible();
  await expect(
    page.getByLabel("Admin users context").locator("[data-tooltip]").filter({
      hasText: "Per-domain viewers",
    }),
  ).toHaveAttribute("data-tooltip", /explicit domain grants/);
  await expect(page.getByLabel("Admin users").getByText("admin@retos.dev")).toBeVisible();
  await expect(
    page.getByLabel("Admin users").locator("summary").filter({ hasText: "Create user" }),
  ).toHaveAttribute("data-tooltip", /account creation/);
  await expect(
    page.getByLabel("Admin users").locator("summary").filter({ hasText: "User directory" }),
  ).toHaveAttribute("data-tooltip", /Review users/);
  await page.getByLabel("Admin users").locator("summary").filter({ hasText: "Create user" }).click();
  await page.getByLabel("New admin email").fill("ui-admin@retos.dev");
  await page.getByLabel("New admin password").fill("ui-admin-password");
  await page.getByLabel("New admin role").selectOption("viewer");
  await page.getByRole("button", { name: "Create admin" }).click();
  const uiAdminRow = page
    .getByLabel("Admin users")
    .locator(".admin-user-row")
    .filter({ hasText: "ui-admin@retos.dev" });
  await expect(uiAdminRow.getByText("ui-admin@retos.dev", { exact: true })).toBeVisible();
  await expect(uiAdminRow.getByText("viewer", { exact: true })).toBeVisible();
  await expect(uiAdminRow.getByText("No domain grants")).toBeVisible();
  await uiAdminRow.getByLabel("Role for ui-admin@retos.dev").selectOption("admin");
  await uiAdminRow.getByRole("button", { name: "Update role" }).click();
  await expect(uiAdminRow.getByText("admin", { exact: true })).toBeVisible();
  await expect(page.getByText("Updated role for ui-admin@retos.dev")).toBeVisible();
  await uiAdminRow.getByLabel("Grant domain to ui-admin@retos.dev").selectOption("domain-123");
  await uiAdminRow.getByRole("button", { name: "Grant" }).click();
  await expect(uiAdminRow.locator(".grant-chip").getByText("smoke-research")).toBeVisible();
  await uiAdminRow.getByPlaceholder("New password").fill("ui-admin-password-2");
  await uiAdminRow.getByRole("button", { name: "Reset" }).click();
  await expect(page.getByText("Updated password for ui-admin@retos.dev")).toBeVisible();
  await uiAdminRow.getByRole("button", { name: "Deactivate" }).click();
  await expect(uiAdminRow.getByText("inactive")).toBeVisible();

  await page.getByRole("link", { name: "Documents" }).first().click();
  await expect(
    page.locator("#documents").getByRole("heading", { name: "Domains and documents" }),
  ).toBeVisible();
  await expect(page.getByLabel("Documents modules").getByRole("link", { name: "Library" })).toHaveAttribute(
    "href",
    "#documents-library",
  );
  await expect(page.getByLabel("Document library context").getByText("Smoke Research")).toBeVisible();
  await expect(page.getByLabel("Document library context").getByText("Active only")).toBeVisible();
  await expect(
    page.getByLabel("Create domain").locator("summary").filter({ hasText: "Create" }),
  ).toHaveAttribute("data-tooltip", /creation form/);
  await expect(
    page.getByLabel("Current workspace editor").locator("summary").filter({ hasText: "Active" }),
  ).toHaveAttribute("data-tooltip", /selected domain/);
  expect(await page.getByLabel("Create domain").evaluate((node) => (node as HTMLDetailsElement).open)).toBe(
    false,
  );
  expect(
    await page
      .getByLabel("Current workspace editor")
      .evaluate((node) => (node as HTMLDetailsElement).open),
  ).toBe(true);
  await expect(
    page.getByLabel("Document library context").locator("[data-tooltip]").filter({
      hasText: "Visible documents",
    }),
  ).toHaveAttribute("data-tooltip", /archive visibility filter/);
  await expect(page.getByLabel("Active domain")).toHaveValue("domain-123");
  await expect(page.getByLabel("Domain documents").getByText("Corpus")).toBeVisible();
  await expect(page.getByLabel("Domain documents").getByText("Documents", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Domain documents").getByText("1 visible")).toHaveAttribute(
    "data-tooltip",
    /selected domain/,
  );
  const documentLibraryLayout = await page.locator("#documents").evaluate((panel) => {
    const style = getComputedStyle(panel);
    const library = panel.querySelector("#documents-library");
    const documentList = panel.querySelector(".document-list:not([hidden])");
    return {
      columns: style.gridTemplateColumns.split(" ").filter(Boolean).length,
      horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      panelScrollHeight: panel.scrollHeight,
      panelClientHeight: panel.clientHeight,
      libraryScrollHeight: library?.scrollHeight ?? 0,
      libraryClientHeight: library?.clientHeight ?? 0,
      documentListScrollHeight: documentList?.scrollHeight ?? 0,
      documentListClientHeight: documentList?.clientHeight ?? 0,
      tooltipCount: panel.querySelectorAll("[data-tooltip]").length,
    };
  });
  expect(documentLibraryLayout.columns).toBeGreaterThanOrEqual(2);
  expect(documentLibraryLayout.horizontalOverflow).toBe(false);
  expect(documentLibraryLayout.panelScrollHeight).toBeLessThanOrEqual(
    documentLibraryLayout.panelClientHeight + 120,
  );
  expect(documentLibraryLayout.libraryClientHeight).toBeGreaterThan(0);
  expect(documentLibraryLayout.documentListClientHeight).toBeGreaterThan(0);
  expect(documentLibraryLayout.libraryScrollHeight).toBeLessThanOrEqual(
    documentLibraryLayout.libraryClientHeight + 320,
  );
  expect(documentLibraryLayout.documentListScrollHeight).toBeLessThanOrEqual(
    documentLibraryLayout.documentListClientHeight + 120,
  );
  expect(documentLibraryLayout.tooltipCount).toBeGreaterThanOrEqual(12);
  await expect(page.getByText("Smoke Document")).toBeVisible();
  await page.getByLabel("Documents modules").getByRole("link", { name: "Sources" }).click();
  await expect(page.getByLabel("Document sources context").getByText("Smoke Research")).toBeVisible();
  await expect(page.getByLabel("Document sources context").getByText("Local rebuild")).toBeVisible();
  await expect(
    page.getByLabel("Document sources context").locator("[data-tooltip]").filter({
      hasText: "Registered sources",
    }),
  ).toHaveAttribute("data-tooltip", /audit evidence/);
  await expect(
    page.getByLabel("Domain sources").locator("summary").filter({ hasText: "Add source" }),
  ).toHaveAttribute("data-tooltip", /source registration/);
  await expect(
    page.getByLabel("Domain sources").locator("summary").filter({ hasText: "Registered sources" }),
  ).toHaveAttribute("data-tooltip", /scan controls/);
  await page.getByLabel("Domain sources").locator("summary").filter({ hasText: "Registered sources" }).click();
  await expect(page.getByLabel("Domain sources").getByText("Corpus inputs", { exact: true })).toBeVisible();
  await expect(
    page.getByLabel("Domain sources").locator(".source-list-heading").getByText("Registered sources"),
  ).toBeVisible();
  await expect(page.getByLabel("Domain sources").getByText("1 registered")).toHaveAttribute(
    "data-tooltip",
    /active domain/,
  );
  await expect(page.getByLabel("Domain sources").getByText("Mounted Corpus")).toBeVisible();
  await page.getByLabel("Documents modules").getByRole("link", { name: "Library" }).click();
  await page.getByRole("button", { name: "Evidence Smoke Document" }).click();
  await expect(page.getByLabel("Evidence for Smoke Document").getByText("v1")).toBeVisible();
  await expect(page.getByLabel("Artifacts for Smoke Document").getByText("raw_text")).toBeVisible();
  await expect(
    page.getByLabel("Artifacts for Smoke Document").getByText("memory://smoke-doc#raw-text"),
  ).toBeVisible();
  await expect(page.getByLabel("Segments for Smoke Document").getByText("page=1")).toBeVisible();
  await expect(
    page.getByLabel("Segments for Smoke Document").getByText("Smoke segment text for search readiness."),
  ).toBeVisible();
  await page.getByLabel("Documents modules").getByRole("link", { name: "Upload" }).click();
  await expect(page.getByLabel("File upload")).toBeVisible();
  await expect(page.getByLabel("Upload ingestion context").getByText("Smoke Research")).toBeVisible();
  await expect(
    page.getByLabel("Upload ingestion context").locator("[data-tooltip]").filter({
      hasText: "TXT, Markdown, PDF",
    }),
  ).toHaveAttribute("data-tooltip", /validated locally/);

  await page.getByRole("link", { name: "Queries" }).first().click();
  await expect(page.getByLabel("Queries modules").getByRole("link", { name: "Live" })).toHaveAttribute(
    "data-tooltip",
    /SSE progress/,
  );
  await page.getByLabel("Queries modules").getByRole("link", { name: "Live" }).click();
  await expect(page.getByRole("button", { name: "Connect live updates" })).toBeVisible();
  await expect(page.getByLabel("Live progress context").getByText("SSE stream")).toBeVisible();
  await expect(
    page.getByLabel("Live progress context").locator("[data-tooltip]").filter({
      hasText: "Persisted progress",
    }),
  ).toHaveAttribute("data-tooltip", /durable audit records/);
  await expect(page.getByLabel("Live progress summary").getByText("Waiting")).toBeVisible();
  await page.getByLabel("Queries modules").getByRole("link", { name: "Ask" }).click();
  await expect(page.getByLabel("Query run context").getByText("Smoke Research")).toBeVisible();
  await expect(page.getByLabel("Query run context").getByText("Local Deep Agents")).toBeVisible();
  await expect(
    page.getByLabel("Query run context").locator("[data-tooltip]").filter({
      hasText: "Citations and budget",
    }),
  ).toHaveAttribute("data-tooltip", /query plans/);
  await page
    .getByRole("textbox", { name: "Question", exact: true })
    .fill("What evidence mentions search readiness?");
  await page.getByRole("button", { name: "Run grounded query" }).click();

  await expect(page.getByText("Grounded answer for:")).toBeVisible();
  await expect(page.getByLabel("Query budget usage").getByText("Within budget")).toBeVisible();
  await expect(page.getByLabel("Query budget usage").getByText("Evidence linked 1/1")).toBeVisible();
  await expect(page.getByLabel("Query budget usage").getByText("Contradictions 0")).toBeVisible();
  await expect(page.getByLabel("Query budget usage").getByText("Citations 1/5")).toBeVisible();
  await expect(page.getByLabel("Query budget usage").getByText("Route single segment")).toBeVisible();
  await page.getByText("Query plan", { exact: true }).click();
  await expect(page.getByLabel("Query plan").getByText("multi hop evidence route")).toBeVisible();
  await expect(page.getByLabel("Query plan").getByText("expects multi document")).toBeVisible();
  await expect(page.getByLabel("Query plan").getByText("evidence mentions readiness search")).toBeVisible();
  await page.getByText("Evidence route", { exact: true }).click();
  await expect(page.getByLabel("Evidence route").getByText("single citation")).toBeVisible();
  await expect(page.getByLabel("Evidence route").getByText("Smoke Document")).toBeVisible();
  await page.getByText("Multi-hop audit", { exact: true }).click();
  await expect(page.getByLabel("Multi-hop audit").getByText("supported multi document")).toBeVisible();
  await expect(page.getByLabel("Multi-hop audit").getByText("multi-hop question")).toBeVisible();
  await expect(page.getByLabel("Multi-hop audit").getByText("Bridge terms: search, readiness")).toBeVisible();
  await page.getByText("Citations", { exact: true }).click();
  await expect(page.getByLabel("Query citations").getByText("Smoke Document")).toBeVisible();
  await page.getByText("Neighbor context", { exact: true }).click();
  await expect(page.getByLabel("Neighbor context").getByText("Adjacent context")).toBeVisible();
  await expect(page.getByLabel("Query citations").getByText("page=1")).toBeVisible();

  await page.getByLabel("Queries modules").getByRole("link", { name: "Live" }).click();
  await page.getByRole("button", { name: "Connect live updates" }).click();
  await expect(page.getByLabel("Live progress summary").getByText("agent.started")).toBeVisible();
  await expect(page.getByLabel("Live progress summary").getByText("2 live events")).toBeVisible();
  await expect(page.getByLabel("Live progress summary").getByText("1 queued")).toBeVisible();
  await expect(page.getByLabel("Live progress events").getByText("Persisted progress replayed")).toBeVisible();
  await expect(page.getByLabel("Live progress events").getByText("Agent query started")).toBeVisible();

  await page.getByRole("link", { name: "Documents" }).first().click();
  await page.getByLabel("Create domain").locator("summary").filter({ hasText: "Create" }).click();
  await page.getByLabel("Slug").fill("policy-research");
  await page.getByPlaceholder("Legal research").fill("Policy Research");
  await page.getByRole("textbox", { name: "Description", exact: true }).fill("Created from the console");
  await page.getByRole("button", { name: "Create domain" }).click();

  await expect(page.getByLabel("Active domain")).toHaveValue("domain-456");
  await expect(
    page.getByLabel("Active domain").getByRole("option", { name: "Policy Research" }),
  ).toBeAttached();
  await page.getByLabel("Domain name").fill("Policy Review");
  await page.getByLabel("Domain description").fill("Updated from the console");
  await page.getByRole("button", { name: "Save domain" }).click();
  await expect(
    page.getByLabel("Active domain").getByRole("option", { name: "Policy Review" }),
  ).toBeAttached();

  await page.getByLabel("Documents modules").getByRole("link", { name: "Sources" }).click();
  await page.getByPlaceholder("Research corpus").fill("Policy Corpus");
  await page.getByLabel("URI").fill("file:///corpus/policy");
  await page.getByRole("button", { name: "Add source" }).click();
  await expect(page.getByLabel("Domain sources").getByText("Policy Corpus")).toBeVisible();
  await page.getByRole("button", { name: "Edit Policy Corpus" }).click();
  await page.getByLabel("Source name for Policy Corpus").fill("Policy Corpus Reviewed");
  await page.getByLabel("Source URI for Policy Corpus").fill("file:///corpus/policy-reviewed");
  await page.getByRole("button", { name: "Save Policy Corpus" }).click();
  await expect(page.getByLabel("Domain sources").getByText("Policy Corpus Reviewed")).toBeVisible();
  await expect(page.getByLabel("Domain sources").getByText("file:///corpus/policy-reviewed")).toBeVisible();

  await page.getByLabel("Domain sources").getByRole("button", { name: "Scan" }).first().click();
  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toContain('Remove source "Policy Corpus Reviewed"');
    await dialog.accept();
  });
  await page.getByRole("button", { name: "Remove Policy Corpus Reviewed" }).click();
  await expect(page.getByLabel("Domain sources").getByText("Policy Corpus Reviewed")).toBeHidden();
  await page.getByLabel("Documents modules").getByRole("link", { name: "Library" }).click();
  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toContain('Archive domain "Policy Review"');
    await dialog.accept();
  });
  await page.getByRole("button", { name: "Archive domain" }).click();
  await expect(page.getByText("This domain is archived.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Save domain" })).toBeDisabled();
  await page.getByRole("button", { name: "Restore domain" }).click();
  await expect(page.getByText("This domain is archived.")).toBeHidden();
  await page.getByLabel("Documents modules").getByRole("link", { name: "Sources" }).click();

  await page.getByRole("button", { name: "Rebuild index" }).click();

  await page.getByLabel("Documents modules").getByRole("link", { name: "Upload" }).click();
  await page.getByLabel("Upload file").setInputFiles({
    name: "rejected-fixture.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Rejected fixture text for browser smoke."),
  });
  await page.getByPlaceholder("Uploaded research note").fill("Rejected Fixture");
  await page.getByRole("button", { name: "Queue upload" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Only .txt, .md, and .pdf files can be uploaded",
  );

  await page.getByLabel("Upload file").setInputFiles({
    name: "uploaded-fixture.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Uploaded fixture text for browser smoke."),
  });
  await page.getByPlaceholder("Uploaded research note").fill("Uploaded Fixture");
  await page.getByRole("button", { name: "Queue upload" }).click();
  await expect(page.getByLabel("Domain documents").getByText("Uploaded Fixture")).toBeVisible();
  await page.getByRole("button", { name: "Edit Uploaded Fixture" }).click();
  await page.getByLabel("Document title for Uploaded Fixture").fill("Uploaded Fixture Reviewed");
  await page.getByRole("button", { name: "Save Uploaded Fixture" }).click();
  await expect(page.getByLabel("Domain documents").getByText("Uploaded Fixture Reviewed")).toBeVisible();
  await page.getByRole("button", { name: "Archive Uploaded Fixture Reviewed" }).click();
  await expect(page.getByLabel("Domain documents").getByText("Uploaded Fixture Reviewed")).toBeHidden();
  await page.getByLabel("Show archived", { exact: true }).check();
  await expect(page.getByLabel("Domain documents").getByText("Uploaded Fixture Reviewed")).toBeVisible();
  await page.getByRole("button", { name: "Restore Uploaded Fixture Reviewed" }).click();
  await expect(page.getByRole("button", { name: "Archive Uploaded Fixture Reviewed" })).toBeVisible();
  await page.getByRole("button", { name: "History Uploaded Fixture Reviewed" }).click();
  await expect(page.getByLabel("History for Uploaded Fixture Reviewed").getByText("document.updated")).toBeVisible();
  await expect(page.getByLabel("History for Uploaded Fixture Reviewed").getByText("Uploaded Fixture Reviewed")).toBeVisible();
  await page.getByRole("button", { name: "History Uploaded Fixture Reviewed" }).click();
  await page.getByLabel("Show archived", { exact: true }).uncheck();
  await expect(page.getByLabel("Domain documents").getByText("Uploaded Fixture Reviewed")).toBeVisible();

  await page.getByLabel("Documents modules").getByRole("link", { name: "Text" }).click();
  await expect(page.getByLabel("Pasted text context").getByText("Policy Review")).toBeVisible();
  await expect(
    page.getByLabel("Pasted text context").locator("[data-tooltip]").filter({
      hasText: "Queued ingestion",
    }),
  ).toHaveAttribute("data-tooltip", /journal/);
  await page.getByPlaceholder("Research note", { exact: true }).fill("Policy Note");
  await page
    .getByPlaceholder("Paste local fixture text, notes, transcripts, or extracted content.")
    .fill("A policy note that can be ingested without touching paid providers.");
  await page.getByRole("button", { name: "Queue text ingestion" }).click();
  await expect(page.getByLabel("Domain documents").getByText("Policy Note")).toBeVisible();

  await page.getByRole("link", { name: "Audit" }).first().click();
  await expect(
    page.locator("#audit").getByRole("heading", { name: "Jobs and evidence ledger" }),
  ).toBeVisible();
  await expect(page.getByLabel("Audit modules").getByRole("link", { name: "Events" })).toHaveAttribute(
    "href",
    "#audit-events",
  );
  await expect(page.getByLabel("Audit jobs context").getByText("Visible jobs")).toBeVisible();
  await expect(
    page.getByLabel("Audit jobs context").locator("[data-tooltip]").filter({
      hasText: "make audit-export-check",
    }),
  ).toHaveAttribute("data-tooltip", /without calling external services/);
  await expect(page.getByLabel("Recent jobs").getByText("job-text-1")).toBeVisible();
  await expect(page.getByText("title: Policy Note")).toBeVisible();
  await page.getByRole("button", { name: "Refresh audit" }).click();
  await page.getByLabel("Audit modules").getByRole("link", { name: "Events" }).click();
  await expect(page.getByLabel("Audit events context").getByText("Journal rows")).toBeVisible();
  await expect(page.getByLabel("Audit events context").getByText("Hash-chain evidence")).toBeVisible();
  await expect(
    page.getByLabel("Audit events context").locator("[data-tooltip]").filter({
      hasText: "Hash-chain evidence",
    }),
  ).toHaveAttribute("data-tooltip", /persisted journal chain/);
  await expect(page.getByLabel("Journal events").getByText("job.created").first()).toBeVisible();
  await expect(page.getByLabel("Journal events").getByText("Hash 2222222222222222")).toBeVisible();
  await expect(page.getByLabel("Journal events").getByText("document.archived")).toBeVisible();
  await expect(page.getByLabel("Journal events").getByText("document.restored")).toBeVisible();
  await expect(page.getByLabel("Journal events").getByText("job-text-1")).toBeVisible();
  await expect(
    page.getByLabel("Persisted progress events").getByText("Queued ingest.source").first(),
  ).toBeVisible();
  await page.getByLabel("Audit modules").getByRole("link", { name: "Progress", exact: true }).click();
  await expect(page.getByLabel("Audit progress context").getByText("Grouped jobs")).toBeVisible();
  await expect(page.getByLabel("Audit progress context").getByText("Progress events")).toBeVisible();
  await expect(
    page.getByLabel("Audit progress context").locator("[data-tooltip]").filter({
      hasText: "Progress events",
    }),
  ).toHaveAttribute("data-tooltip", /replay and audit/);
  const scanProgressGroup = page
    .getByLabel("Progress grouped by job")
    .locator("article")
    .filter({ hasText: "job-scan-1" });
  await expect(scanProgressGroup.getByText("Completed ingest.source")).toBeVisible();
  await expect(scanProgressGroup.getByText("3")).toBeVisible();
  await page.getByLabel("Audit modules").getByRole("link", { name: "Jobs" }).click();
  await page.getByRole("button", { name: "Export audit" }).click();
  await expect(page.getByText("retos-audit-export.json:")).toBeVisible();
  await expect(page.getByLabel("Audit export integrity").getByText("Export integrity")).toBeVisible();
  await expect(page.getByLabel("Audit export integrity").getByText("valid")).toBeVisible();
  await expect(page.getByLabel("Audit export integrity").getByText("retos.audit-export.v2")).toBeVisible();
  await expect(page.getByLabel("Audit export integrity").getByText("make audit-export-check")).toBeVisible();
  await expect(page.getByLabel("Audit export integrity").getByText("Continuity gaps")).toBeVisible();
  await expect(page.getByLabel("Audit export integrity").getByText("0").first()).toBeVisible();

  await page.getByRole("link", { name: "Evals" }).first().click();
  await expect(page.getByLabel("Evals modules").getByRole("link", { name: "History" })).toHaveAttribute(
    "data-tooltip",
    /regression-gate/,
  );
  await expect(page.getByLabel("Active eval scope").getByText("Dataset reports")).toBeVisible();
  await expect(
    page.getByLabel("Active eval scope").locator("[data-tooltip]").filter({
      hasText: "No paid calls",
    }),
  ).toHaveAttribute("data-tooltip", /mocked providers/);
  await page.getByRole("button", { name: "Run eval smoke" }).click();
  await expect(page.getByLabel("Eval results context").getByText("retos-smoke")).toBeVisible();
  await expect(
    page.getByLabel("Eval results context").locator("[data-tooltip]").filter({
      hasText: "Cases",
    }),
  ).toHaveAttribute("data-tooltip", /pass\/fail evidence/);
  await expect(page.getByLabel("Eval metrics").getByText("retrieval recall")).toBeVisible();
  await expect(page.getByLabel("Eval metadata").getByText("built-in")).toBeVisible();
  await expect(page.getByLabel("Eval metadata").getByText("retos-smoke-fixtures")).toBeVisible();
  await expect(page.getByLabel("Eval cases").getByText("apollo-guidance")).toBeVisible();
  await page.getByLabel("Evals modules").getByRole("link", { name: "History" }).click();
  await expect(page.getByLabel("Eval history context").getByText("Comparable runs")).toBeVisible();
  await expect(
    page.getByLabel("Eval history context").locator("[data-tooltip]").filter({
      hasText: "Trend suites",
    }),
  ).toHaveAttribute("data-tooltip", /persisted suite history/);
  await expect(page.getByLabel("Eval run history").getByText("retos-smoke")).toBeVisible();
  await expect(page.getByLabel("Eval run history").getByText("3 cases")).toBeVisible();
  await expect(page.getByLabel("Eval trends").getByText("retos-smoke")).toBeVisible();
  await expect(page.getByLabel("Eval trends").getByText("retrieval recall")).toBeVisible();

  await page.getByLabel("Evals modules").getByRole("link", { name: "Run", exact: true }).click();
  await page.getByRole("button", { name: "Run agent multi-hop" }).click();
  await expect(page.getByLabel("Eval metrics").getByText("multi hop support")).toBeVisible();
  await expect(page.getByLabel("Eval metadata").getByText("agent-multihop-fixtures")).toBeVisible();
  await expect(page.getByLabel("Eval cases").getByText("apollo-telemetry-bridge")).toBeVisible();
  await expect(page.getByLabel("Eval cases").getByText("invoice-retention-policy")).toBeVisible();
  await expect(page.getByLabel("Eval cases").getByText("incident-escalation-triage")).toBeVisible();
  await page.getByLabel("Evals modules").getByRole("link", { name: "History" }).click();
  await expect(page.getByLabel("Eval run history").getByText("agent-multihop")).toBeVisible();
  await expect(page.getByLabel("Eval trends").getByText("agent-multihop")).toBeVisible();
  const agentEvalRunRow = page
    .getByLabel("Eval run history")
    .locator("article")
    .filter({ hasText: "agent-multihop" });
  await expect(agentEvalRunRow.getByText("3 cases")).toBeVisible();

  await page.getByLabel("Evals modules").getByRole("link", { name: "Run", exact: true }).click();
  await page.getByLabel("Eval domain scope").selectOption("domain-123");
  await expect(page.getByLabel("Active eval scope").getByText("Smoke Research")).toHaveCount(2);
  await page.getByLabel("SQuAD dataset path").fill("ui-squad.json");
  await page.getByLabel("SQuAD max cases").fill("2");
  await page.getByLabel("SQuAD report stem").fill("ui-squad");
  await page.getByRole("button", { name: "Run SQuAD eval" }).click();
  await expect(page.getByLabel("Eval metadata").getByText("squad-v2")).toBeVisible();
  await expect(page.getByLabel("Eval metadata").getByText("/evals/datasets/ui-squad.json")).toBeVisible();
  await expect(page.getByLabel("Eval cases").getByText("squad-mars-red-planet")).toBeVisible();
  await expect(page.getByLabel("Eval report paths").getByText("ui-squad.json")).toBeVisible();
  await expect(page.getByLabel("Eval report paths").getByText("ui-squad.md")).toBeVisible();
  await page.getByLabel("Evals modules").getByRole("link", { name: "History" }).click();
  await expect(page.getByLabel("Eval run history").getByText("squad-v2")).toBeVisible();
  const squadEvalRunRow = page
    .getByLabel("Eval run history")
    .locator("article")
    .filter({ hasText: "squad-v2" });
  await expect(squadEvalRunRow.getByText("Smoke Research")).toBeVisible();
  await expect(page.getByLabel("Eval run history").getByText("retos-smoke")).toHaveCount(0);
  await expect(page.getByLabel("Eval run history").getByText("2 cases")).toBeVisible();

  await page.getByLabel("Evals modules").getByRole("link", { name: "Run", exact: true }).click();
  await page.locator("summary").filter({ hasText: "HotpotQA" }).click();
  await page.getByLabel("HotpotQA dataset path").fill("ui-hotpotqa.json");
  await page.getByLabel("HotpotQA max cases").fill("1");
  await page.getByLabel("HotpotQA report stem").fill("ui-hotpotqa");
  await page.getByRole("button", { name: "Run HotpotQA eval" }).click();
  await expect(page.getByLabel("Eval cases").getByText("hotpotqa-vela-air-force")).toBeVisible();
  await expect(page.getByLabel("Eval report paths").getByText("ui-hotpotqa.json")).toBeVisible();
  await expect(page.getByLabel("Eval report paths").getByText("ui-hotpotqa.md")).toBeVisible();
  await page.getByLabel("Evals modules").getByRole("link", { name: "History" }).click();
  await expect(page.getByLabel("Eval run history").getByText("hotpotqa")).toBeVisible();
  const hotpotqaEvalRunRow = page
    .getByLabel("Eval run history")
    .locator("article")
    .filter({ hasText: "hotpotqa" });
  await expect(hotpotqaEvalRunRow.getByText("1 cases")).toBeVisible();

  await page.getByLabel("Evals modules").getByRole("link", { name: "Run", exact: true }).click();
  await page.getByLabel("HotpotQA report stem").fill("ui-hotpotqa-agent");
  await page.getByRole("button", { name: "Run HotpotQA agent" }).click();
  await expect(page.getByLabel("Eval cases").getByText("hotpotqa-agent-vela-air-force")).toBeVisible();
  await expect(page.getByLabel("Eval metadata").getByText("hotpotqa-agent")).toBeVisible();
  await expect(page.getByLabel("Eval report paths").getByText("ui-hotpotqa-agent.json")).toBeVisible();
  await expect(page.getByLabel("Eval report paths").getByText("ui-hotpotqa-agent.md")).toBeVisible();
  await page.getByLabel("Evals modules").getByRole("link", { name: "History" }).click();
  await expect(page.getByLabel("Eval run history").getByText("hotpotqa-agent")).toBeVisible();

  await page.getByLabel("Evals modules").getByRole("link", { name: "Run", exact: true }).click();
  await page.locator("summary").filter({ hasText: "Natural Questions" }).click();
  await page.getByLabel("Natural Questions dataset path").fill("ui-nq.jsonl");
  await page.getByLabel("Natural Questions max cases").fill("1");
  await page.getByLabel("Natural Questions report stem").fill("ui-natural-questions");
  await page.getByRole("button", { name: "Run Natural Questions eval" }).click();
  await expect(page.getByLabel("Eval cases").getByText("natural-questions-123")).toBeVisible();
  await expect(page.getByLabel("Eval report paths").getByText("ui-natural-questions.json")).toBeVisible();
  await expect(page.getByLabel("Eval report paths").getByText("ui-natural-questions.md")).toBeVisible();
  await page.getByLabel("Evals modules").getByRole("link", { name: "History" }).click();
  await expect(page.getByLabel("Eval run history").getByText("natural-questions")).toBeVisible();

  await page.getByLabel("Evals modules").getByRole("link", { name: "Run", exact: true }).click();
  await page.locator("summary").filter({ hasText: "OCR benchmark" }).click();
  await page.getByLabel("OCR benchmark path").fill("ocr-benchmark/manifest.json");
  await page.getByLabel("OCR benchmark format").selectOption("manifest");
  await page.getByLabel("OCR benchmark max cases").fill("1");
  await page.getByLabel("OCR benchmark report stem").fill("ui-ocr-benchmark");
  await page.getByRole("button", { name: "Run OCR benchmark" }).click();
  await expect(page.getByLabel("Eval metrics").getByText("character error rate")).toBeVisible();
  await expect(page.getByLabel("Eval cases").getByText("receipt-001")).toBeVisible();
  await expect(page.getByLabel("Eval report paths").getByText("ui-ocr-benchmark.json")).toBeVisible();
  await expect(page.getByLabel("Eval report paths").getByText("ui-ocr-benchmark.md")).toBeVisible();
  await page.getByLabel("Evals modules").getByRole("link", { name: "History" }).click();
  await expect(page.getByLabel("Eval run history").getByText("ocr-manifest")).toBeVisible();

  await page.getByRole("button", { name: "Rerun ocr-manifest" }).click();
  await page.getByLabel("Evals modules").getByRole("link", { name: "History" }).click();
  await expect(page.getByLabel("Eval run history").getByText("ocr-manifest")).toHaveCount(2);
  await expect(page.getByLabel("Eval trends").getByText("2 runs")).toBeVisible();

  await page.getByRole("button", { name: "Compare latest" }).click();
  await expect(page.getByLabel("Eval comparison").getByText("retos-smoke")).toBeVisible();
  await expect(page.getByLabel("Eval comparison").getByText("squad-v2")).toBeVisible();
  await expect(page.getByLabel("Eval comparison").getByText("retrieval recall")).toBeVisible();
  await expect(page.getByLabel("Eval comparison").getByText("unchanged")).toBeVisible();

  await page.getByRole("button", { name: "Regression gate" }).click();
  await expect(page.getByLabel("Eval regression gate").getByText("Promote")).toBeVisible();
  await expect(page.getByLabel("Eval regression gate").getByText("0 metric regressions")).toBeVisible();
  await expect(page.getByLabel("Eval regression gate").getByText("retrieval recall")).toBeVisible();
  await expect(page.getByLabel("Eval regression gate").getByText("2%")).toBeVisible();

  await page.getByRole("link", { name: "Audit" }).first().click();
  await page.getByLabel("Filter jobs").selectOption("index.domain");
  await expect(page.getByLabel("Recent jobs").getByText("job-index-1")).toBeVisible();
  await page
    .getByLabel("Recent jobs")
    .locator("article")
    .filter({ hasText: "job-index-1" })
    .getByRole("button", { name: "Inspect" })
    .click();
  await expect(page.getByLabel("Selected job detail").getByText("job-index-1")).toBeVisible();
  await expect(
    page.getByLabel("Selected job detail").getByText("index.domain", { exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Selected job detail").getByText("requested_at")).toBeVisible();
  await expect(page.getByLabel("Selected job detail").getByText("Queued index.domain")).toBeVisible();
  await page
    .getByLabel("Recent jobs")
    .locator("article")
    .filter({ hasText: "job-failed-index-1" })
    .getByRole("button", { name: "Retry" })
    .click();
  await expect(page.getByLabel("Selected job detail").getByText("job-retry-job-failed-index-1")).toBeVisible();
  await expect(page.getByLabel("Selected job detail").getByText("retried_from_job_id")).toBeVisible();
  await expect(page.getByLabel("Selected job detail").locator("pre")).toContainText(
    '"retried_from_job_id": "job-failed-index-1"',
  );

  await page.getByRole("link", { name: "Queries" }).first().click();
  await page.getByLabel("Queries modules").getByRole("link", { name: "Live" }).click();
  await page.getByRole("button", { name: "Connect live updates" }).click();
  await expect(
    page.getByLabel("Live progress events").locator(".event-row").filter({ hasText: "job.queued" }),
  ).toHaveCount(1);
  await expect(page.getByText("Resume progress:progress")).toBeVisible();
  await expect(page.getByLabel("Live progress events").getByText("Agent query started")).toBeVisible();
});

test("keeps provider controls usable on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();

  await page.keyboard.press("Tab");
  const skipLink = page.getByRole("link", { name: "Skip to workspace" });
  await expect(skipLink).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#overview")).toBeFocused();

  await page.getByRole("link", { name: "Admin" }).first().click();
  await expect(page.locator("#admin").getByRole("heading", { name: "LLM providers" })).toBeVisible();
  await page.getByLabel("Password", { exact: true }).fill("retos-dev-admin-change-me");
  await page.getByRole("button", { name: "Load providers" }).click();

  await expect(page.getByLabel("Available LLM providers").getByText("Ollama local runtime")).toBeVisible();
  await page.getByRole("link", { name: "Evals" }).first().click();
  await expect(page.locator("#evals").getByRole("heading", { name: "Local evals" })).toBeVisible();
  await page.getByRole("link", { name: "Audit" }).first().click();
  await expect(
    page.locator("#audit").getByRole("heading", { name: "Jobs and evidence ledger" }),
  ).toBeVisible();
  const hasHorizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(hasHorizontalOverflow).toBe(false);
});
