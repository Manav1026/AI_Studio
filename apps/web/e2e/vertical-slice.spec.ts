import { expect, test } from "@playwright/test";

// Acceptance flow: sign in → connect Salesforce → sync → explore catalog → ask → validate → execute → save → reuse.
test("core vertical slice", async ({ page }) => {
  const email = `e2e-${Date.now()}@e2e-${Date.now()}.example.com`;
  const shots = process.env.SHOTS_DIR;

  await page.goto("/login");
  await page.getByLabel("Work email").fill(email);
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();

  await page.goto("/connections");
  await page.getByRole("button", { name: "Connect Salesforce" }).click();
  await expect(page.getByText("Connected. Metadata sync has been queued.")).toBeVisible();
  await expect(page.getByText("succeeded").first()).toBeVisible({ timeout: 20_000 });
  if (shots) await page.screenshot({ path: `${shots}/02-connections.png`, fullPage: true });

  await page.goto("/catalog");
  await expect(page.getByRole("link", { name: "Opportunity" })).toBeVisible();
  if (shots) await page.screenshot({ path: `${shots}/03-catalog.png`, fullPage: true });
  await page.getByRole("link", { name: "Opportunity" }).click();
  await expect(page.getByRole("heading", { name: /Fields \(\d+\)/ })).toBeVisible();
  if (shots) await page.screenshot({ path: `${shots}/04-object.png`, fullPage: true });

  await page.goto("/query");
  await page.getByLabel("Question").fill("Show me the top 10 customers by opportunity revenue this year");
  await page.getByRole("button", { name: "Generate query" }).click();
  await expect(page.getByText("validated").first()).toBeVisible();
  await expect(page.getByLabel(/SOQL/)).toHaveValue(/GROUP BY Account\.Name/);
  await page.getByRole("button", { name: "Execute" }).click();
  await expect(page.getByRole("button", { name: "Save as reusable query" })).toBeVisible();
  await expect(page.locator("table tbody tr")).toHaveCount(10);
  if (shots) await page.screenshot({ path: `${shots}/05-query.png`, fullPage: true });
  await page.getByRole("button", { name: "Save as reusable query" }).click();
  await expect(page.getByText(/Saved as/)).toBeVisible();

  // repeated question is answered from the saved template (no AI call)
  await page.getByLabel("Question").fill("top 5 customers by opportunity revenue last year");
  await page.getByRole("button", { name: "Generate query" }).click();
  await expect(page.getByText("saved template")).toBeVisible();
  await expect(page.getByLabel(/SOQL/)).toHaveValue(/LAST_YEAR/);

  await page.goto("/saved");
  await expect(page.getByRole("button", { name: "Run" }).first()).toBeVisible();
  await page.getByRole("button", { name: "Run" }).first().click();
  await expect(page.getByText(/\d+ rows ·/)).toBeVisible();
  if (shots) await page.screenshot({ path: `${shots}/06-saved.png`, fullPage: true });

  await page.goto("/history");
  await expect(page.getByText("template").first()).toBeVisible();
  await page.goto("/audit");
  await expect(page.getByText("query.execute").first()).toBeVisible();
  if (shots) await page.screenshot({ path: `${shots}/07-audit.png`, fullPage: true });
  await page.goto("/");
  await expect(page.getByText("Saved-query reuse")).toBeVisible();
  if (shots) await page.screenshot({ path: `${shots}/01-overview.png`, fullPage: true });
});
