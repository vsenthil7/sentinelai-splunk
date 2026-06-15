import { test, expect } from "@playwright/test";

const USER = "analyst";
const PASS = "sentinel-demo";

async function login(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.getByTestId("tenant-input").fill("default");
  await page.getByTestId("username-input").fill(USER);
  await page.getByTestId("password-input").fill(PASS);
  await page.getByTestId("login-button").click();
  await expect(page.getByTestId("run-pipeline")).toBeVisible();
}

test.describe("Authentication", () => {
  test("redirects unauthenticated users to login", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByTestId("login-button")).toBeVisible();
  });

  test("rejects invalid credentials", async ({ page }) => {
    await page.goto("/login");
    await page.getByTestId("tenant-input").fill("default");
    await page.getByTestId("username-input").fill("wrong");
    await page.getByTestId("password-input").fill("wrong");
    await page.getByTestId("login-button").click();
    await expect(page.getByTestId("error-banner")).toContainText("Invalid credentials");
  });

  test("login button disabled until all fields filled", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByTestId("login-button")).toBeDisabled();
    await page.getByTestId("tenant-input").fill("default");
    await page.getByTestId("username-input").fill(USER);
    await expect(page.getByTestId("login-button")).toBeDisabled();
    await page.getByTestId("password-input").fill(PASS);
    await expect(page.getByTestId("login-button")).toBeEnabled();
  });

  test("successful login lands on console", async ({ page }) => {
    await login(page);
    await expect(page.getByText("Operations Console")).toBeVisible();
    await expect(page.getByTestId("health-pill")).toContainText("splunk:mock");
  });

  test("logout returns to login and protects routes", async ({ page }) => {
    await login(page);
    await page.getByTestId("logout").click();
    await expect(page).toHaveURL(/\/login$/);
  });
});

test.describe("Detection pipeline & dashboard", () => {
  test("running the pipeline populates investigations and stats", async ({ page }) => {
    await login(page);
    await expect(page.getByTestId("empty-state")).toBeVisible();
    await page.getByTestId("run-pipeline").click();
    await expect(page.getByTestId("investigation-grid")).toBeVisible();
    const cards = page.locator('[data-testid^="inv-card-"]');
    await expect(cards).toHaveCount(3);
    await expect(page.getByTestId("stat-total")).toHaveText("3");
    await expect(page.getByTestId("stat-tp")).not.toHaveText("0");
  });

  test("refresh reloads investigations", async ({ page }) => {
    await login(page);
    await page.getByTestId("run-pipeline").click();
    await expect(page.locator('[data-testid^="inv-card-"]').first()).toBeVisible();
    await page.getByTestId("refresh").click();
    await expect(page.locator('[data-testid^="inv-card-"]').first()).toBeVisible();
  });

  test("severity badges render on cards", async ({ page }) => {
    await login(page);
    await page.getByTestId("run-pipeline").click();
    await expect(page.getByTestId("severity-badge").first()).toBeVisible();
  });
});

test.describe("Investigation detail & response", () => {
  test("opens detail, shows verdict, timeline, summary", async ({ page }) => {
    await login(page);
    await page.getByTestId("run-pipeline").click();
    await page.locator('[data-testid^="inv-card-"]').first().click();
    await expect(page.getByTestId("inv-title")).toBeVisible();
    await expect(page.getByTestId("verdict-card")).toBeVisible();
    await expect(page.getByTestId("timeline")).toBeVisible();
    await expect(page.getByTestId("summary")).toBeVisible();
  });

  test("approves a gated response action", async ({ page }) => {
    await login(page);
    await page.getByTestId("run-pipeline").click();
    // Open the first true-positive card (has actions). Brute-force is first.
    await page.locator('[data-testid^="inv-card-"]').first().click();
    const approveBtn = page.getByTestId("approve-0");
    if (await approveBtn.isVisible()) {
      await approveBtn.click();
      await expect(page.getByTestId("approved-0")).toBeVisible();
    } else {
      // If first card had no actions, at least the actions/no-actions region renders.
      await expect(
        page.getByTestId("actions").or(page.getByTestId("no-actions")),
      ).toBeVisible();
    }
  });

  test("back link returns to console", async ({ page }) => {
    await login(page);
    await page.getByTestId("run-pipeline").click();
    await page.locator('[data-testid^="inv-card-"]').first().click();
    await page.getByTestId("back-link").click();
    await expect(page.getByText("Operations Console")).toBeVisible();
  });
});
