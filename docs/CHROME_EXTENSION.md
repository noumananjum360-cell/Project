# Chrome extension (Manifest V3)

## What it does

* **Popup:** connection settings (backend + dashboard URL), sign-in, connection and AI status, "Analyze with BidGenie" / "Write with AI" for the current tab, open side panel, open dashboard.
* **Content script** (only on `https://www.upwork.com/jobs/*` and `/freelance-jobs/apply/*`): adds two buttons in a closed shadow root. **Nothing is read until you click.** It then extracts the visible title, description, budget, skills, level and basic client signals, and shows results in an injected panel with an editable proposal and a copy button.
* **Side panel:** the same results for the active tab, with retry and dashboard links.
* **Background service worker:** the only context that calls the backend. It saves the job (`POST /jobs/from-extension`, reusing duplicates), analyzes it, and optionally generates a proposal.

The extension **never** clicks page buttons, fills application forms, submits proposals, spends Connects, runs in the background on its own, or reads unrelated pages or browsing history.

## Security

* Minimal permissions: `storage`, `sidePanel`; host access only to the two job-page patterns and local backends. Other backends require HTTPS and a runtime permission prompt (`optional_host_permissions`).
* No secrets in the bundle. The OpenAI key stays on the server. The access token lives in `chrome.storage.session` (restricted to trusted contexts) and the rotating refresh token in `chrome.storage.local`.
* Every runtime message is validated (`src/shared/messages.ts`): its shape, field limits, URL schemes, money formats, action allow-list and sender. Content scripts may only send `JOB_EXTRACTED`, and only from supported pages.
* Expired sessions refresh transparently once; on failure the user is asked to sign in again.
* Content-script UI uses a closed shadow root, so page scripts can't read results.

## Build and load

```bash
cd extension
npm ci
npm run build          # dist/
npm run package        # bidgenie-extension.zip
```

1. `chrome://extensions` → enable **Developer mode** → **Load unpacked** → select `extension/dist`.
2. Open the popup → **Connection settings**: backend `http://localhost:8000` (dev) and dashboard `http://localhost:5173` (Vite) or `http://localhost:8080` (Docker).
3. Sign in with your BidGenie account.

For production, use `https://` URLs. Chrome asks you to allow access to that origin.

## Testing

* `npm test`: extraction against **representative HTML fixtures** (`tests/fixtures`), message validation, and token refresh/duplicate handling in the API client.
* `npx playwright test`: loads `dist/` into Chromium, starts a real backend (demo mode), signs in through the popup, serves a fixture at an upwork.com URL via request interception, clicks the injected button, and verifies the job, analysis and proposal through the backend API.

**Live Upwork pages have not been tested.** Page markup changes over time; if extraction fails, the extension says so, and you can paste the job into the dashboard. Use the extension only in ways allowed by the platform's terms.
