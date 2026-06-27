import { expect, test } from "@playwright/test";

const ADMIN_USER = process.env.E2E_ADMIN_USER ?? "admin";
const ADMIN_PASS = process.env.E2E_ADMIN_PASS ?? "admin";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    try {
      window.localStorage.clear();
    } catch {}
  });
});

test("rejects wrong credentials", async ({ page }) => {
  await page.goto("/");
  await page.getByPlaceholder("Username").fill("admin");
  await page.getByPlaceholder("Password").fill("definitely-wrong-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Unsuccessful")).toBeVisible({ timeout: 15_000 });
});

test("logs in and reaches the console", async ({ page }) => {
  await page.goto("/");
  await page.getByPlaceholder("Username").fill(ADMIN_USER);
  await page.getByPlaceholder("Password").fill(ADMIN_PASS);
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByText("Sign in was successful.")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByPlaceholder("Username")).toBeHidden({ timeout: 15_000 });
});
