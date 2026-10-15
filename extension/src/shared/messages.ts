/**
 * Message contracts between extension contexts, with runtime validation.
 * Every message received by the background worker is validated here before use.
 */
import type { ExtractedJob } from "./types";

export type Action = "analyze" | "write";

export type Message =
  | { type: "GET_STATUS" }
  | { type: "GET_CONFIG" }
  | { type: "SET_CONFIG"; backendUrl: string; dashboardUrl: string }
  | { type: "LOGIN"; email: string; password: string }
  | { type: "LOGOUT" }
  | { type: "GET_TAB_STATE"; tabId: number }
  | { type: "RUN_ON_TAB"; tabId: number; action: Action }
  | { type: "JOB_EXTRACTED"; action: Action; job: ExtractedJob }
  | { type: "PING_PAGE" }
  | { type: "EXTRACT_JOB"; action: Action }
  | { type: "TAB_STATE_CHANGED"; tabId: number };

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const isStr = (v: unknown, max = 20000): v is string => typeof v === "string" && v.length <= max;
const isNullableStr = (v: unknown, max = 2000) => v === null || isStr(v, max);
const isAction = (v: unknown): v is Action => v === "analyze" || v === "write";
const isTabId = (v: unknown): v is number => typeof v === "number" && Number.isInteger(v) && v >= 0;
const isMoney = (v: unknown) => v === null || (typeof v === "string" && /^\d{1,9}(\.\d{1,2})?$/.test(v));

export function isValidUrl(v: string, allowHttp = true): boolean {
  try {
    const u = new URL(v);
    return u.protocol === "https:" || (allowHttp && u.protocol === "http:");
  } catch {
    return false;
  }
}

export function isExtractedJob(v: unknown): v is ExtractedJob {
  if (!isObj(v)) return false;
  return (
    isStr(v.title, 300) &&
    v.title.trim().length >= 3 &&
    isStr(v.description, 20000) &&
    v.description.trim().length >= 20 &&
    (v.url === null || (isStr(v.url, 1000) && isValidUrl(v.url, false))) &&
    isMoney(v.budget_min) &&
    isMoney(v.budget_max) &&
    isStr(v.currency, 3) &&
    /^[A-Z]{3}$/.test(v.currency) &&
    ["hourly", "fixed", "unknown"].includes(v.job_type as string) &&
    Array.isArray(v.required_skills) &&
    v.required_skills.length <= 40 &&
    v.required_skills.every((s) => isStr(s, 60)) &&
    ["entry", "intermediate", "expert", "unknown"].includes(v.experience_level as string) &&
    (v.client_info === null || isObj(v.client_info)) &&
    isNullableStr(v.proposals_info, 200)
  );
}

/** Validate an untrusted message. Returns null when the shape is not recognised. */
export function parseMessage(v: unknown): Message | null {
  if (!isObj(v) || typeof v.type !== "string") return null;
  switch (v.type) {
    case "GET_STATUS":
    case "GET_CONFIG":
    case "LOGOUT":
    case "PING_PAGE":
      return { type: v.type };
    case "SET_CONFIG":
      return isStr(v.backendUrl, 500) && isValidUrl(v.backendUrl) && isStr(v.dashboardUrl, 500) && isValidUrl(v.dashboardUrl)
        ? { type: "SET_CONFIG", backendUrl: v.backendUrl, dashboardUrl: v.dashboardUrl }
        : null;
    case "LOGIN":
      return isStr(v.email, 320) && isStr(v.password, 128) ? { type: "LOGIN", email: v.email, password: v.password } : null;
    case "GET_TAB_STATE":
      return isTabId(v.tabId) ? { type: "GET_TAB_STATE", tabId: v.tabId } : null;
    case "RUN_ON_TAB":
      return isTabId(v.tabId) && isAction(v.action) ? { type: "RUN_ON_TAB", tabId: v.tabId, action: v.action } : null;
    case "JOB_EXTRACTED":
      return isAction(v.action) && isExtractedJob(v.job) ? { type: "JOB_EXTRACTED", action: v.action, job: v.job } : null;
    case "EXTRACT_JOB":
      return isAction(v.action) ? { type: "EXTRACT_JOB", action: v.action } : null;
    case "TAB_STATE_CHANGED":
      return isTabId(v.tabId) ? { type: "TAB_STATE_CHANGED", tabId: v.tabId } : null;
    default:
      return null;
  }
}

export const SUPPORTED_PAGE_PATTERNS = [/^https:\/\/www\.upwork\.com\/jobs\//, /^https:\/\/www\.upwork\.com\/freelance-jobs\/apply\//];

export function isSupportedPage(url: string | undefined | null): boolean {
  return !!url && SUPPORTED_PAGE_PATTERNS.some((r) => r.test(url));
}
