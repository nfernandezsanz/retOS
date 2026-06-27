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
  const jobs = [jobFixture("job-seed-1", "ingest.source", "succeeded")];
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
  const evalRuns: { job: ReturnType<typeof jobFixture>; report: typeof evalReport | null }[] = [];

  function recordAudit(job: ReturnType<typeof jobFixture>) {
    journalEvents.unshift({
      id: `journal-${job.id}`,
      occurred_at: "2026-06-27T00:01:00Z",
      actor: "admin@retos.dev",
      event_type: "job.created",
      entity_type: "job",
      entity_id: job.id,
      payload: { kind: job.kind, status: job.status },
    });
    progressEvents.unshift({
      id: `progress-${job.id}`,
      job_id: job.id,
      occurred_at: "2026-06-27T00:01:00Z",
      event_type: "job.queued",
      message: `Queued ${job.kind}`,
      payload: { status: job.status },
    });
  }

  await page.route("http://localhost:8000/auth/login", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: { access_token: "test-token", token_type: "bearer" },
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
        payload: { domain_id: documents[index].domain_id, title_changed: true },
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
        payload: { domain_id: documents[index].domain_id },
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
  await page.route("http://localhost:8000/evals/runs?limit=6", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: evalRuns,
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

  await page.getByLabel("Password").fill("retos-dev-admin-change-me");
  await page.getByRole("button", { name: "Load providers" }).click();

  await expect(page.getByText("ollama:gemma4")).toBeVisible();
  await expect(page.getByText("Ollama local runtime")).toBeVisible();
  await expect(page.getByText("OpenAI")).toBeVisible();
  await expect(page.getByText("Blocked")).toBeVisible();
  await expect(page.getByLabel("Active domain")).toHaveValue("domain-123");
  await expect(page.getByText("Smoke Document")).toBeVisible();
  await expect(page.getByLabel("Domain sources").getByText("Mounted Corpus")).toBeVisible();

  await page
    .getByLabel("Question")
    .fill("What evidence mentions search readiness?");
  await page.getByRole("button", { name: "Run grounded query" }).click();

  await expect(page.getByText("Grounded answer for:")).toBeVisible();
  await expect(page.getByLabel("Query citations").getByText("Smoke Document")).toBeVisible();
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
  await expect(page.getByLabel("Journal events").getByText("job-text-1")).toBeVisible();
  await expect(
    page.getByLabel("Persisted progress events").getByText("Queued ingest.source").first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "Export audit" }).click();
  await expect(page.getByText("retos-audit-export.json:")).toBeVisible();

  await page.getByRole("button", { name: "Run eval smoke" }).click();
  await expect(page.getByLabel("Eval metrics").getByText("retrieval recall")).toBeVisible();
  await expect(page.getByLabel("Eval cases").getByText("apollo-guidance")).toBeVisible();
  await expect(page.locator("#evals").getByText("eval.run succeeded")).toBeVisible();
  await expect(page.getByLabel("Eval run history").getByText("retos-smoke")).toBeVisible();
  await expect(page.getByLabel("Eval run history").getByText("3 cases")).toBeVisible();

  await page.getByLabel("SQuAD dataset path").fill("ui-squad.json");
  await page.getByLabel("SQuAD max cases").fill("2");
  await page.getByLabel("SQuAD report stem").fill("ui-squad");
  await page.getByRole("button", { name: "Run SQuAD eval" }).click();
  await expect(page.getByLabel("Eval cases").getByText("squad-mars-red-planet")).toBeVisible();
  await expect(page.getByLabel("Eval run history").getByText("squad-v2")).toBeVisible();
  await expect(page.getByLabel("Eval run history").getByText("2 cases")).toBeVisible();
  await expect(page.getByLabel("Eval report paths").getByText("ui-squad.json")).toBeVisible();
  await expect(page.getByLabel("Eval report paths").getByText("ui-squad.md")).toBeVisible();

  await page.getByLabel("Filter jobs").selectOption("index.domain");
  await expect(page.getByLabel("Recent jobs").getByText("job-index-1")).toBeVisible();

  await page.getByRole("button", { name: "Connect live updates" }).click();
  await expect(page.getByLabel("Live progress events").getByText("job.queued")).toBeVisible();
  await expect(page.getByText("Resume progress:progress")).toBeVisible();
  await expect(page.getByLabel("Live progress events").getByText("Agent query started")).toBeVisible();
});

test("keeps provider controls usable on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();

  await expect(page.getByRole("heading", { name: "LLM providers" })).toBeVisible();
  await page.getByLabel("Password").fill("retos-dev-admin-change-me");
  await page.getByRole("button", { name: "Load providers" }).click();

  await expect(page.getByText("Ollama local runtime")).toBeVisible();
  const hasHorizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(hasHorizontalOverflow).toBe(false);
});
