import { expect, test } from "@playwright/test";

test("mobile layout has no horizontal overflow and a working menu", async ({ page }) => {
  await page.goto("/");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);

  const email = `mobile-${Date.now()}@example.com`;
  await page.goto("/register");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill("CorrectHorse9Battery");
  await page.getByLabel("Confirm password").fill("CorrectHorse9Battery");
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/onboarding/);

  for (const path of ["/dashboard", "/jobs", "/tracker", "/analytics", "/settings"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const o = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(o, `horizontal overflow on ${path}`).toBeLessThanOrEqual(0);
  }

  await page.getByRole("button", { name: "Open menu" }).click();
  await page.getByRole("complementary", { name: "Navigation menu" }).getByRole("link", { name: "Portfolio" }).click();
  await expect(page).toHaveURL(/\/portfolio$/);
});
