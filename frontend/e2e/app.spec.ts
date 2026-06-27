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
      created_at: "2026-06-27T00:00:00Z",
      updated_at: "2026-06-27T00:00:00Z",
    },
  ];
  const jobs = [jobFixture("job-seed-1", "ingest.source", "succeeded")];

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
    await route.fulfill({
      contentType: "application/json",
      json: documents.filter((document) => document.domain_id === domainId),
    });
  });
  await page.route(/http:\/\/localhost:8000\/jobs\?limit=\d+/, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: jobs,
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
    await route.fulfill({
      contentType: "application/json",
      status: 202,
      json: job,
    });
  });
  await page.route(/http:\/\/localhost:8000\/domains\/[^/]+\/index\/rebuild/, async (route) => {
    jobs.unshift(jobFixture("job-index-1", "index.domain", "queued", { requested_at: "now" }));
    await route.fulfill({
      contentType: "application/json",
      status: 202,
      json: jobs[0],
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
      created_at: "2026-06-27T00:00:00Z",
      updated_at: "2026-06-27T00:00:00Z",
    });
    jobs.unshift(jobFixture("job-text-1", "ingest.source", "queued", { title: "Policy Note" }));
    await route.fulfill({
      contentType: "application/json",
      status: 202,
      json: jobs[0],
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
  await page.route("http://localhost:8000/events/progress", async (route) => {
    await route.fulfill({
      contentType: "text/event-stream",
      body: [
        "id: 1",
        "event: system.ready",
        'data: {"id":1,"event":"system.ready","data":{"message":"RetOS API is ready"}}',
        "",
        "id: 2",
        "event: agent.started",
        'data: {"id":2,"event":"agent.started","data":{"job_id":"job-query-1","status":"running","message":"Agent query started"}}',
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

  await page.getByPlaceholder("Research note").fill("Policy Note");
  await page
    .getByPlaceholder("Paste local fixture text, notes, transcripts, or extracted content.")
    .fill("A policy note that can be ingested without touching paid providers.");
  await page.getByRole("button", { name: "Queue text ingestion" }).click();
  await expect(page.getByLabel("Queued jobs").getByText("ingest.source queued")).toBeVisible();
  await expect(page.getByLabel("Domain documents").getByText("Policy Note")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Jobs and evidence ledger" })).toBeVisible();
  await expect(page.getByLabel("Recent jobs").getByText("job-text-1")).toBeVisible();
  await expect(page.getByText("title: Policy Note")).toBeVisible();

  await page.getByLabel("Filter jobs").selectOption("index.domain");
  await expect(page.getByLabel("Recent jobs").getByText("job-index-1")).toBeVisible();

  await page.getByRole("button", { name: "Connect live updates" }).click();
  await expect(page.getByLabel("Live progress events").getByText("system.ready")).toBeVisible();
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
