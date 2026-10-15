import { expect, test, type Page } from "@playwright/test";

const PASSWORD = "CorrectHorse9Battery";
const unique = () => `${Date.now()}${Math.floor(Math.random() * 1000)}`;

async function register(page: Page, email: string, base = "") {
  await page.goto(`${base}/register`);
  await page.getByLabel("Full name").fill("E2E Freelancer");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByLabel("Confirm password").fill(PASSWORD);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/onboarding$/);
}

async function addJob(page: Page, title: string, base = "") {
  await page.goto(`${base}/jobs`);
  await page.getByRole("button", { name: "Add jobs" }).click();
  await page.getByLabel("Job title").fill(title);
  await page
    .getByLabel("Job description")
    .fill(
      "We need an experienced developer to build an analytics dashboard. Requirements: React front end with TypeScript, " +
        "FastAPI backend and PostgreSQL. Deliverables include charts, filters and authentication. Milestones agreed up front.",
    );
  const skills = page.getByLabel("Required skills");
  for (const s of ["React", "TypeScript", "FastAPI", "PostgreSQL"]) {
    await skills.fill(s);
    await skills.press("Enter");
  }
  await page.getByLabel("Job type").selectOption("hourly");
  await page.getByLabel("Budget min").fill("50");
  await page.getByLabel("Budget max").fill("80");
  await page.getByLabel("Experience level").selectOption("expert");
  await page.getByRole("button", { name: "Save job" }).click();
  await expect(page).toHaveURL(/\/jobs\/[0-9a-f-]{36}$/);
}

test("complete freelancer workflow persists across refreshes", async ({ page }) => {
  await register(page, `e2e-${unique()}@example.com`);

  // Onboarding: skip resume, fill profile, add a project, finish.
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByLabel("Professional headline").fill("Full-stack developer (React, FastAPI)");
  const primary = page.getByLabel("Primary skills");
  for (const s of ["React", "TypeScript", "FastAPI", "PostgreSQL"]) {
    await primary.fill(s);
    await primary.press("Enter");
  }
  await page.getByLabel("Years of experience").fill("6");
  await page.getByLabel("Hourly rate").fill("60");
  await page.getByRole("button", { name: "Save and continue" }).click();

  await page.getByLabel("Project title").fill("Inventory dashboard for a retail team");
  await page
    .getByLabel("Description")
    .fill("Built a React and TypeScript dashboard with a FastAPI backend and PostgreSQL to track inventory and orders.");
  const pskills = page.getByLabel("Skills & technologies");
  for (const s of ["React", "FastAPI"]) {
    await pskills.fill(s);
    await pskills.press("Enter");
  }
  await page.getByRole("button", { name: "Add project" }).click();
  await expect(page.getByText("1 project added.")).toBeVisible();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Go to dashboard" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByText(/AI results are/)).toBeVisible(); // demo-mode banner is shown

  // Import + analyze.
  await addJob(page, "React + FastAPI analytics dashboard");
  await page.getByRole("button", { name: "Analyze job" }).first().click();
  await expect(page.getByRole("img", { name: /Fit Score: \d+ out of 100/ })).toBeVisible();
  await expect(page.getByText("Strong Match").first()).toBeVisible();
  await expect(page.getByText("Inventory dashboard for a retail team").first()).toBeVisible(); // portfolio retrieval
  await expect(page.getByText("Simulated AI").first()).toBeVisible();

  // Generate, edit, autosave.
  await page.getByRole("button", { name: "Write proposal" }).click();
  await page.getByRole("button", { name: "Generate proposal" }).click();
  await expect(page).toHaveURL(/\/proposals\/[0-9a-f-]{36}$/);
  const editor = page.getByLabel("Proposal text");
  await expect(editor).toContainText("Inventory dashboard for a retail team");
  await editor.fill("My edited proposal text written by hand for E2E.");
  await expect(page.getByText("All changes saved")).toBeVisible({ timeout: 10_000 });

  // Survives a refresh.
  await page.reload();
  await expect(page.getByLabel("Proposal text")).toHaveValue("My edited proposal text written by hand for E2E.");

  // Track and update status.
  await page.getByRole("button", { name: "Mark Ready to Submit" }).click();
  await expect(page.getByText(/Marked Ready to Submit/)).toBeVisible();
  await page.goto("/tracker");
  await page.getByLabel("Move React + FastAPI analytics dashboard to status").selectOption("sent");
  await expect(page.getByText("Moved to Sent.")).toBeVisible();

  // Dashboard reflects persisted data.
  await page.goto("/dashboard");
  const card = (label: string) => page.locator("div.rounded-xl", { has: page.getByText(label, { exact: true }) });
  await expect(card("Imported jobs")).toContainText("1");
  await expect(card("Jobs analyzed")).toContainText("1");
  await expect(card("Proposals generated")).toContainText("1");
  await expect(card("Proposals sent")).toContainText("1");
});

test("users cannot access each other's records", async ({ page, browser }) => {
  await register(page, `owner-${unique()}@example.com`);
  await addJob(page, "Private job of the owner");
  const jobUrl = page.url();

  const other = await browser.newContext();
  const p2 = await other.newPage();
  await register(p2, `intruder-${unique()}@example.com`);
  await p2.goto(new URL(jobUrl).pathname);
  await expect(p2.getByText("Job not found")).toBeVisible();
  await expect(p2.getByText("Private job of the owner")).toHaveCount(0);
  await other.close();
});

test("useful error when AI credentials are absent", async ({ page }) => {
  const base = "http://localhost:5175";
  await register(page, `noai-${unique()}@example.com`, base);
  await page.goto(`${base}/dashboard`);
  await expect(page.getByText(/AI features are not configured on the server/)).toBeVisible();
  await addJob(page, "Job analyzed without AI", base);
  await page.getByRole("button", { name: "Analyze job" }).first().click();
  await expect(page.getByText(/AI features are not configured\. Set OPENAI_API_KEY/)).toBeVisible();
});
