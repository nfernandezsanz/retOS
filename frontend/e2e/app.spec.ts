import { expect, type Page, test } from "@playwright/test";

function jobFixture(id: string, kind: string, status: string, payload = {}) {
  return {
    id,
    kind,
    status,
    domain_id: "domain-123",
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
  const failedIndexJob = {
    ...jobFixture("job-failed-index-1", "index.domain", "failed", {
      requested_at: "fixture",
    }),
    error: "fixture failure",
    completed_at: "2026-06-27T00:01:00Z",
  };
  const jobs = [jobFixture("job-seed-1", "ingest.source", "succeeded"), failedIndexJob];
  const journalEvents = [
    {
      id: "journal-seed-1",
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

  function buildEvalTrends() {
    const grouped = new Map<string, typeof evalRuns>();
    for (const run of evalRuns.slice().reverse()) {
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
        job_id: job.id,
        occurred_at: `${baseTime}20Z`,
        event_type: `job.${job.status}`,
        message: `Completed ${job.kind}`,
        payload: { status: job.status },
      },
      {
        id: `progress-${job.id}-started`,
        job_id: job.id,
        occurred_at: `${baseTime}10Z`,
        event_type: `${job.kind}.started`,
        message: `Started ${job.kind}`,
        payload: { status: "running" },
      },
      {
        id: `progress-${job.id}-queued`,
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
      occurred_at: "2026-06-27T00:01:00Z",
      actor: "admin@retos.dev",
      event_type: eventType,
      entity_type: "admin_user",
      entity_id: adminUserId,
      payload: { domain_id: domainId },
    });
  }

  await page.route("http://localhost:8000/auth/login", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: { access_token: "test-token", token_type: "bearer" },
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
        providers: [
          {
            name: "local",
            label: "Ollama local runtime",
            default_model: "gemma4",
            configured: true,
            enabled: true,
            paid: false,
            reason: null,
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
            base_url: null,
          },
        ],
      },
    });
  });
  await page.route("http://localhost:8000/domains", async (route) => {
    if (route.request().method() === "POST") {
      const created = {
        id: "domain-456",
        slug: "policy-research",
        name: "Policy Research",
        description: "Created from the console",
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

    await route.fulfill({
      contentType: "application/json",
      json: domains,
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
        schema_version: "retos.audit-export.v1",
        generated_at: "2026-06-27T00:02:00Z",
        limit: 200,
        journal_events: journalEvents,
        progress_events: progressEvents,
      },
    });
  });
  await page.route(/http:\/\/localhost:8000\/domains\/[^/]+\/sources/, async (route) => {
    const domainId = new URL(route.request().url()).pathname.split("/")[2];
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
    const job = jobFixture("job-eval-1", "eval.run", "succeeded", { result: evalReport });
    jobs.unshift(job);
    evalRuns.unshift({ job, report: evalReport });
    recordAudit(job);
    await route.fulfill({
      contentType: "application/json",
      status: 202,
      json: { job, report: evalReport },
    });
  });
  await page.route("http://localhost:8000/evals/squad", async (route) => {
    const reportPaths = {
      json: "/var/lib/retos/evals/reports/ui-squad.json",
      markdown: "/var/lib/retos/evals/reports/ui-squad.md",
    };
    const job = jobFixture("job-eval-squad-1", "eval.run", "succeeded", {
      dataset_path: "/var/lib/retos/evals/datasets/ui-squad.json",
      max_cases: 2,
      report_paths: reportPaths,
      result: squadReport,
    });
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
    const reportPaths = {
      json: "/var/lib/retos/evals/reports/ui-hotpotqa.json",
      markdown: "/var/lib/retos/evals/reports/ui-hotpotqa.md",
    };
    const job = jobFixture("job-eval-hotpotqa-1", "eval.run", "succeeded", {
      dataset_path: "/var/lib/retos/evals/datasets/ui-hotpotqa.json",
      max_cases: 1,
      report_paths: reportPaths,
      result: hotpotqaReport,
    });
    jobs.unshift(job);
    evalRuns.unshift({ job, report: hotpotqaReport });
    recordAudit(job);
    await route.fulfill({
      contentType: "application/json",
      status: 202,
      json: { job, report: hotpotqaReport, report_paths: reportPaths },
    });
  });
  await page.route("http://localhost:8000/evals/natural-questions", async (route) => {
    const reportPaths = {
      json: "/var/lib/retos/evals/reports/ui-natural-questions.json",
      markdown: "/var/lib/retos/evals/reports/ui-natural-questions.md",
    };
    const job = jobFixture("job-eval-natural-questions-1", "eval.run", "succeeded", {
      dataset_path: "/var/lib/retos/evals/datasets/ui-nq.jsonl",
      max_cases: 1,
      report_paths: reportPaths,
      result: naturalQuestionsReport,
    });
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
    };
    const reportPaths = {
      json: "/var/lib/retos/evals/reports/ui-ocr-benchmark.json",
      markdown: "/var/lib/retos/evals/reports/ui-ocr-benchmark.md",
    };
    const job = jobFixture("job-eval-ocr-benchmark-1", "eval.run", "succeeded", {
      dataset_path: `/var/lib/retos/evals/datasets/${payload.dataset_path}`,
      dataset_format: payload.dataset_format,
      max_cases: payload.max_cases,
      report_paths: reportPaths,
      result: ocrBenchmarkReport,
    });
    jobs.unshift(job);
    evalRuns.unshift({ job, report: ocrBenchmarkReport });
    recordAudit(job);
    await route.fulfill({
      contentType: "application/json",
      status: 202,
      json: { job, report: ocrBenchmarkReport, report_paths: reportPaths },
    });
  });
  await page.route("http://localhost:8000/evals/runs?limit=6", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: evalRuns,
    });
  });
  await page.route("http://localhost:8000/evals/runs/trends?limit=60", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: buildEvalTrends(),
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
    const job = jobFixture(`job-eval-rerun-${evalRerunCount}`, "eval.run", "succeeded", {
      ...original.job.payload,
      rerun_from_job_id: original.job.id,
    });
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
    await route.fulfill({
      contentType: "application/json",
      json: evalComparison,
    });
  });
  await page.route("http://localhost:8000/events/progress", async (route) => {
    await route.fulfill({
      contentType: "text/event-stream",
      body: [
        "id: progress:progress-seed-1",
        "event: job.queued",
        'data: {"id":"progress:progress-seed-1","event":"job.queued","data":{"job_id":"job-seed-1","message":"Persisted progress replayed"}}',
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

test("loads the operational console", async ({ page }) => {
  await expect(
    page.getByRole("heading", { name: "Auditable document investigation" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Refresh workspace" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Documents" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Domains and documents" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Run grounded query" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Connect live updates" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Local evals" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "LLM providers" })).toBeVisible();

  await page.getByLabel("Password", { exact: true }).fill("retos-dev-admin-change-me");
  await page.getByRole("button", { name: "Load providers" }).click();

  await expect(page.getByText("ollama:gemma4")).toBeVisible();
  await expect(page.getByText("Ollama local runtime")).toBeVisible();
  await expect(page.getByText("OpenAI")).toBeVisible();
  await expect(page.getByText("Blocked")).toBeVisible();
  await expect(page.getByLabel("Admin users").getByText("admin@retos.dev")).toBeVisible();
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
  await uiAdminRow.getByLabel("Grant domain to ui-admin@retos.dev").selectOption("domain-123");
  await uiAdminRow.getByRole("button", { name: "Grant" }).click();
  await expect(uiAdminRow.locator(".grant-chip").getByText("smoke-research")).toBeVisible();
  await uiAdminRow.getByPlaceholder("New password").fill("ui-admin-password-2");
  await uiAdminRow.getByRole("button", { name: "Reset" }).click();
  await expect(page.getByText("Updated password for ui-admin@retos.dev")).toBeVisible();
  await uiAdminRow.getByRole("button", { name: "Deactivate" }).click();
  await expect(uiAdminRow.getByText("inactive")).toBeVisible();
  await expect(page.getByLabel("Active domain")).toHaveValue("domain-123");
  await expect(page.getByText("Smoke Document")).toBeVisible();
  await expect(page.getByLabel("Domain sources").getByText("Mounted Corpus")).toBeVisible();

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
  await expect(page.getByLabel("Evidence route").getByText("single citation")).toBeVisible();
  await expect(page.getByLabel("Evidence route").getByText("Smoke Document")).toBeVisible();
  await expect(page.getByLabel("Multi-hop audit").getByText("supported multi document")).toBeVisible();
  await expect(page.getByLabel("Multi-hop audit").getByText("multi-hop question")).toBeVisible();
  await expect(page.getByLabel("Multi-hop audit").getByText("Bridge terms: search, readiness")).toBeVisible();
  await expect(page.getByLabel("Query citations").getByText("Smoke Document")).toBeVisible();
  await expect(page.getByLabel("Neighbor context").getByText("Adjacent context")).toBeVisible();
  await expect(page.getByText("page=1")).toBeVisible();

  await page.getByLabel("Slug").fill("policy-research");
  await page.getByPlaceholder("Legal research").fill("Policy Research");
  await page.getByLabel("Description").fill("Created from the console");
  await page.getByRole("button", { name: "Create domain" }).click();

  await expect(page.getByLabel("Active domain")).toHaveValue("domain-456");
  await expect(page.getByRole("option", { name: "Policy Research" })).toBeAttached();

  await page.getByPlaceholder("Research corpus").fill("Policy Corpus");
  await page.getByLabel("URI").fill("file:///corpus/policy");
  await page.getByRole("button", { name: "Add source" }).click();
  await expect(page.getByLabel("Domain sources").getByText("Policy Corpus")).toBeVisible();

  await page.getByLabel("Domain sources").getByRole("button", { name: "Scan" }).first().click();
  await expect(page.getByLabel("Queued jobs").getByText("ingest.source queued")).toBeVisible();

  await page.getByRole("button", { name: "Rebuild index" }).click();
  await expect(page.getByLabel("Queued jobs").getByText("index.domain queued")).toBeVisible();

  await page.getByLabel("Upload file").setInputFiles({
    name: "uploaded-fixture.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Uploaded fixture text for browser smoke."),
  });
  await page.getByPlaceholder("Uploaded research note").fill("Uploaded Fixture");
  await page.getByRole("button", { name: "Queue upload" }).click();
  await expect(page.getByLabel("Domain documents").getByText("Uploaded Fixture")).toBeVisible();
  await expect(page.getByLabel("Recent jobs").getByText("job-upload-1")).toBeVisible();
  await page.getByRole("button", { name: "Edit Uploaded Fixture" }).click();
  await page.getByLabel("Document title for Uploaded Fixture").fill("Uploaded Fixture Reviewed");
  await page.getByRole("button", { name: "Save Uploaded Fixture" }).click();
  await expect(page.getByLabel("Domain documents").getByText("Uploaded Fixture Reviewed")).toBeVisible();
  await page.getByRole("button", { name: "Archive Uploaded Fixture Reviewed" }).click();
  await expect(page.getByLabel("Domain documents").getByText("Uploaded Fixture Reviewed")).toBeHidden();
  await page.getByLabel("Show archived").check();
  await expect(page.getByLabel("Domain documents").getByText("Uploaded Fixture Reviewed")).toBeVisible();
  await page.getByRole("button", { name: "Restore Uploaded Fixture Reviewed" }).click();
  await expect(page.getByRole("button", { name: "Archive Uploaded Fixture Reviewed" })).toBeVisible();
  await page.getByRole("button", { name: "History Uploaded Fixture Reviewed" }).click();
  await expect(page.getByLabel("History for Uploaded Fixture Reviewed").getByText("document.updated")).toBeVisible();
  await expect(page.getByLabel("History for Uploaded Fixture Reviewed").getByText("Uploaded Fixture Reviewed")).toBeVisible();
  await page.getByRole("button", { name: "History Uploaded Fixture Reviewed" }).click();
  await page.getByLabel("Show archived").uncheck();
  await expect(page.getByLabel("Domain documents").getByText("Uploaded Fixture Reviewed")).toBeVisible();

  await page.getByPlaceholder("Research note", { exact: true }).fill("Policy Note");
  await page
    .getByPlaceholder("Paste local fixture text, notes, transcripts, or extracted content.")
    .fill("A policy note that can be ingested without touching paid providers.");
  await page.getByRole("button", { name: "Queue text ingestion" }).click();
  await expect(page.getByLabel("Recent jobs").getByText("job-text-1")).toBeVisible();
  await expect(page.getByLabel("Domain documents").getByText("Policy Note")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Jobs and evidence ledger" })).toBeVisible();
  await expect(page.getByLabel("Recent jobs").getByText("job-text-1")).toBeVisible();
  await expect(page.getByText("title: Policy Note")).toBeVisible();
  await page.getByRole("button", { name: "Refresh audit" }).click();
  await expect(page.getByLabel("Journal events").getByText("job.created").first()).toBeVisible();
  await expect(page.getByLabel("Journal events").getByText("document.archived")).toBeVisible();
  await expect(page.getByLabel("Journal events").getByText("document.restored")).toBeVisible();
  await expect(page.getByLabel("Journal events").getByText("job-text-1")).toBeVisible();
  await expect(
    page.getByLabel("Persisted progress events").getByText("Queued ingest.source").first(),
  ).toBeVisible();
  const scanProgressGroup = page
    .getByLabel("Progress grouped by job")
    .locator("article")
    .filter({ hasText: "job-scan-1" });
  await expect(scanProgressGroup.getByText("Completed ingest.source")).toBeVisible();
  await expect(scanProgressGroup.getByText("3")).toBeVisible();
  await page.getByRole("button", { name: "Export audit" }).click();
  await expect(page.getByText("retos-audit-export.json:")).toBeVisible();

  await page.getByRole("button", { name: "Run eval smoke" }).click();
  await expect(page.getByLabel("Eval metrics").getByText("retrieval recall")).toBeVisible();
  await expect(page.getByLabel("Eval metadata").getByText("built-in")).toBeVisible();
  await expect(page.getByLabel("Eval metadata").getByText("retos-smoke-fixtures")).toBeVisible();
  await expect(page.getByLabel("Eval cases").getByText("apollo-guidance")).toBeVisible();
  await expect(page.locator("#evals").getByText("eval.run succeeded")).toBeVisible();
  await expect(page.getByLabel("Eval run history").getByText("retos-smoke")).toBeVisible();
  await expect(page.getByLabel("Eval run history").getByText("3 cases")).toBeVisible();
  await expect(page.getByLabel("Eval trends").getByText("retos-smoke")).toBeVisible();
  await expect(page.getByLabel("Eval trends").getByText("retrieval recall")).toBeVisible();

  await page.getByLabel("SQuAD dataset path").fill("ui-squad.json");
  await page.getByLabel("SQuAD max cases").fill("2");
  await page.getByLabel("SQuAD report stem").fill("ui-squad");
  await page.getByRole("button", { name: "Run SQuAD eval" }).click();
  await expect(page.getByLabel("Eval metadata").getByText("squad-v2")).toBeVisible();
  await expect(page.getByLabel("Eval metadata").getByText("/evals/datasets/ui-squad.json")).toBeVisible();
  await expect(page.getByLabel("Eval cases").getByText("squad-mars-red-planet")).toBeVisible();
  await expect(page.getByLabel("Eval run history").getByText("squad-v2")).toBeVisible();
  await expect(page.getByLabel("Eval run history").getByText("2 cases")).toBeVisible();
  await expect(page.getByLabel("Eval report paths").getByText("ui-squad.json")).toBeVisible();
  await expect(page.getByLabel("Eval report paths").getByText("ui-squad.md")).toBeVisible();

  await page.getByLabel("HotpotQA dataset path").fill("ui-hotpotqa.json");
  await page.getByLabel("HotpotQA max cases").fill("1");
  await page.getByLabel("HotpotQA report stem").fill("ui-hotpotqa");
  await page.getByRole("button", { name: "Run HotpotQA eval" }).click();
  await expect(page.getByLabel("Eval cases").getByText("hotpotqa-vela-air-force")).toBeVisible();
  await expect(page.getByLabel("Eval run history").getByText("hotpotqa")).toBeVisible();
  await expect(page.getByLabel("Eval run history").getByText("1 cases")).toBeVisible();
  await expect(page.getByLabel("Eval report paths").getByText("ui-hotpotqa.json")).toBeVisible();
  await expect(page.getByLabel("Eval report paths").getByText("ui-hotpotqa.md")).toBeVisible();

  await page.getByLabel("Natural Questions dataset path").fill("ui-nq.jsonl");
  await page.getByLabel("Natural Questions max cases").fill("1");
  await page.getByLabel("Natural Questions report stem").fill("ui-natural-questions");
  await page.getByRole("button", { name: "Run Natural Questions eval" }).click();
  await expect(page.getByLabel("Eval cases").getByText("natural-questions-123")).toBeVisible();
  await expect(page.getByLabel("Eval run history").getByText("natural-questions")).toBeVisible();
  await expect(page.getByLabel("Eval report paths").getByText("ui-natural-questions.json")).toBeVisible();
  await expect(page.getByLabel("Eval report paths").getByText("ui-natural-questions.md")).toBeVisible();

  await page.getByLabel("OCR benchmark path").fill("ocr-benchmark/manifest.json");
  await page.getByLabel("OCR benchmark format").selectOption("manifest");
  await page.getByLabel("OCR benchmark max cases").fill("1");
  await page.getByLabel("OCR benchmark report stem").fill("ui-ocr-benchmark");
  await page.getByRole("button", { name: "Run OCR benchmark" }).click();
  await expect(page.getByLabel("Eval metrics").getByText("character error rate")).toBeVisible();
  await expect(page.getByLabel("Eval cases").getByText("receipt-001")).toBeVisible();
  await expect(page.getByLabel("Eval run history").getByText("ocr-manifest")).toBeVisible();
  await expect(page.getByLabel("Eval report paths").getByText("ui-ocr-benchmark.json")).toBeVisible();
  await expect(page.getByLabel("Eval report paths").getByText("ui-ocr-benchmark.md")).toBeVisible();

  await page.getByRole("button", { name: "Rerun ocr-manifest" }).click();
  await expect(page.getByLabel("Recent jobs").getByText("job-eval-rerun-1")).toBeVisible();
  await expect(page.getByLabel("Eval run history").getByText("ocr-manifest")).toHaveCount(2);
  await expect(page.getByLabel("Eval trends").getByText("2 runs")).toBeVisible();

  await page.getByRole("button", { name: "Compare latest" }).click();
  await expect(page.getByLabel("Eval comparison").getByText("retos-smoke")).toBeVisible();
  await expect(page.getByLabel("Eval comparison").getByText("squad-v2")).toBeVisible();
  await expect(page.getByLabel("Eval comparison").getByText("retrieval recall")).toBeVisible();
  await expect(page.getByLabel("Eval comparison").getByText("unchanged")).toBeVisible();

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

  await page.getByRole("button", { name: "Connect live updates" }).click();
  await expect(page.getByLabel("Live progress events").getByText("job.queued")).toBeVisible();
  await expect(page.getByText("Resume progress:progress")).toBeVisible();
  await expect(page.getByLabel("Live progress events").getByText("Agent query started")).toBeVisible();
});

test("keeps provider controls usable on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();

  await expect(page.getByRole("heading", { name: "LLM providers" })).toBeVisible();
  await page.getByLabel("Password", { exact: true }).fill("retos-dev-admin-change-me");
  await page.getByRole("button", { name: "Load providers" }).click();

  await expect(page.getByText("Ollama local runtime")).toBeVisible();
  const hasHorizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(hasHorizontalOverflow).toBe(false);
});
