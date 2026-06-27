import { expect, type Page, test } from "@playwright/test";

async function mockProviderApi(page: Page) {
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
  await page.route(/http:\/\/localhost:8000\/domains\/[^/]+\/queries/, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: {
        job: {
          id: "job-query-1",
          kind: "agent.query",
          status: "succeeded",
          payload: {},
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
}

test.beforeEach(async ({ page }) => {
  await mockProviderApi(page);
  await page.goto("/");
});

test("loads the operational console", async ({ page }) => {
  await expect(
    page.getByRole("heading", { name: "Auditable document investigation" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Connect live updates" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Documents" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Processing timeline" })).toBeVisible();
  await expect(page.getByRole("list").filter({ hasText: "Discover mounted files" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Run grounded query" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "LLM providers" })).toBeVisible();

  await page.getByLabel("Password").fill("retos-dev-admin-change-me");
  await page.getByRole("button", { name: "Load providers" }).click();

  await expect(page.getByText("ollama:gemma4")).toBeVisible();
  await expect(page.getByText("Ollama local runtime")).toBeVisible();
  await expect(page.getByText("OpenAI")).toBeVisible();
  await expect(page.getByText("Blocked")).toBeVisible();

  await page.getByLabel("Domain ID").fill("domain-123");
  await page
    .getByLabel("Question")
    .fill("What evidence mentions search readiness?");
  await page.getByRole("button", { name: "Run grounded query" }).click();

  await expect(page.getByText("Grounded answer for:")).toBeVisible();
  await expect(page.getByText("Smoke Document")).toBeVisible();
  await expect(page.getByText("page=1")).toBeVisible();
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
