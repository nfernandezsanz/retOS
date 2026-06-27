import { expect, test } from "@playwright/test";

test("loads the operational console", async ({ page }) => {
  await page.goto("/");

  await expect(
    page.getByRole("heading", { name: "Auditable document investigation" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Connect live updates" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Documents" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Processing timeline" })).toBeVisible();
  await expect(page.locator('[aria-live="polite"]')).toBeVisible();
  await expect(page.getByRole("button", { name: "Run with Gemma 4" })).toBeVisible();
});
