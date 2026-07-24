import { expect, test } from "@playwright/test";

// Smoke tests: the app loads and the core journey wiring is present. The full
// ask -> stream -> chart flow is exercised against the mock backend in CI.
test("home page renders the chat UI", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "DataChat" })).toBeVisible();
  await expect(page.getByPlaceholder(/CO₂ per capita/i)).toBeVisible();
  await expect(page.getByRole("button", { name: /ask/i })).toBeVisible();
});

test("asking a question streams a result", async ({ page }) => {
  await page.goto("/");
  await page.getByPlaceholder(/CO₂ per capita/i).fill("Top 5 countries by CO2 per capita in 2022");
  await page.getByRole("button", { name: /ask/i }).click();

  // Against the mock backend this resolves quickly; allow generous time for a
  // cold start on the free tier.
  await expect(page.getByText(/Executed SQL/i)).toBeVisible({ timeout: 60_000 });
});
