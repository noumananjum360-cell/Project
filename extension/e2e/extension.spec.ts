/**
 * Browser-level test of the unpacked extension against a real backend.
 * The "job page" is a REPRESENTATIVE FIXTURE served via request interception
 * at an upwork.com URL so the content script is injected; no live site is used.
 */
import { chromium, expect, test, type BrowserContext } from "@playwright/test";
import { existsSync, mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));

const DIST = resolve(HERE, "../dist");
const API = "http://localhost:8000/api/v1";
const PASSWORD = "CorrectHorse9Battery";
const exe = process.env.PLAYWRIGHT_CHROMIUM_PATH ?? "/opt/pw-browsers/chromium";

async function api(path: string, init: RequestInit = {}, token?: string) {
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
  });
  const body = await res.json();
  if (!res.ok) throw new Error(`${path}: ${res.status} ${JSON.stringify(body)}`);
  return body;
}

let context: BrowserContext;

test.beforeAll(async () => {
  expect(existsSync(join(DIST, "manifest.json")), "run `npm run build` first").toBe(true);
  context = await chromium.launchPersistentContext(mkdtempSync(join(tmpdir(), "bg-ext-")), {
    headless: true,
    executablePath: existsSync(exe) ? exe : undefined,
    args: ["--headless=new", `--disable-extensions-except=${DIST}`, `--load-extension=${DIST}`],
  });
});

test.afterAll(async () => context?.close());

test("extension signs in, extracts a job on click, and gets analysis + proposal from the backend", async () => {
  const email = `ext-${Date.now()}@example.com`;
  await api("/auth/register", { method: "POST", body: JSON.stringify({ email, password: PASSWORD }) });
  const login = await api("/auth/login", { method: "POST", body: JSON.stringify({ email, password: PASSWORD, client: "extension" }) });
  const token = login.tokens.access_token as string;
  await api(
    "/profile",
    { method: "PUT", body: JSON.stringify({ primary_skills: ["React", "TypeScript", "FastAPI"], years_experience: 6, hourly_rate: "55" }) },
    token,
  );
  await api(
    "/portfolio",
    {
      method: "POST",
      body: JSON.stringify({ title: "Analytics dashboard (React + FastAPI)", description: "Built a React TypeScript dashboard backed by FastAPI and PostgreSQL.", skills: ["React", "FastAPI"] }),
    },
    token,
  );

  // Find the extension id from its service worker.
  let [sw] = context.serviceWorkers();
  if (!sw) sw = await context.waitForEvent("serviceworker");
  const extId = new URL(sw.url()).host;

  // Sign in through the popup UI.
  const popup = await context.newPage();
  await popup.goto(`chrome-extension://${extId}/popup.html`);
  await expect(popup.getByText(/not signed in/)).toBeVisible();
  await expect(popup.getByText(/AI results are simulated/)).toBeVisible();
  await popup.getByLabel("Email").fill(email);
  await popup.getByLabel("Password").fill(PASSWORD);
  await popup.getByRole("button", { name: "Sign in" }).click();
  await expect(popup.getByText(`Connected as ${email}`)).toBeVisible();

  // Serve the fixture at a supported URL and click the injected "Write with AI" button.
  const html = readFileSync(resolve(HERE, "../tests/fixtures/job-page-data-test.html"), "utf8");
  const page = await context.newPage();
  await page.route("https://www.upwork.com/**", (route) => route.fulfill({ status: 200, contentType: "text/html", body: html }));
  await page.setViewportSize({ width: 1200, height: 800 });
  await page.goto("https://www.upwork.com/jobs/~01e2etest0000000001?source=test");
  await page.waitForFunction(() => !!document.getElementById("bidgenie-ai-root"));
  // The toolbar lives in a closed shadow root (page scripts cannot read results); click by position.
  await page.mouse.click(1200 - 60, 800 - 32); // right-most button: "Write with AI"

  // Verify through the backend that the job, analysis and proposal were created by the extension.
  await expect
    .poll(async () => (await api("/proposals", {}, token)).total, { timeout: 30_000 })
    .toBe(1);
  const jobs = await api("/jobs", {}, token);
  expect(jobs.total).toBe(1);
  expect(jobs.items[0].source).toBe("extension");
  expect(jobs.items[0].title).toBe("Senior React + FastAPI developer for analytics dashboard");
  expect(jobs.items[0].url).toBe("https://www.upwork.com/jobs/~01e2etest0000000001");
  expect(jobs.items[0].latest_fit_score).toBeGreaterThan(0);

  // Popup shows the result for the active tab once brought to front.
  await page.bringToFront();
  const tabState = await sw.evaluate(async () => {
    const all = await chrome.storage.session.get(null);
    return Object.entries(all).find(([k]) => k.startsWith("tab:"))?.[1] as { status: string; analysis: { fit_score: number }; proposal: { content: string } };
  });
  expect(tabState.status).toBe("done");
  expect(tabState.analysis.fit_score).toBe(jobs.items[0].latest_fit_score);
  expect(tabState.proposal.content).toContain("Analytics dashboard (React + FastAPI)");

  // Re-running on the same job reuses the saved record (no duplicate).
  await page.reload(); // results panel shifts the toolbar; start from a clean page
  await page.waitForFunction(() => !!document.getElementById("bidgenie-ai-root"));
  await page.mouse.click(1200 - 60, 800 - 32);
  await expect.poll(async () => (await api("/proposals", {}, token)).total, { timeout: 30_000 }).toBe(2);
  expect((await api("/jobs", {}, token)).total).toBe(1);
});

test("background rejects malformed messages", async () => {
  let [sw] = context.serviceWorkers();
  if (!sw) sw = await context.waitForEvent("serviceworker");
  const extId = new URL(sw.url()).host;
  const p = await context.newPage();
  await p.goto(`chrome-extension://${extId}/popup.html`);
  const res = await p.evaluate(() => chrome.runtime.sendMessage({ type: "RUN_ON_TAB", tabId: 1, action: "submit_proposal" }));
  expect(res).toEqual({ ok: false, error: "Invalid message." });
});
