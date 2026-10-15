/**
 * Extract visible job details from a job page, ONLY when the user asks.
 *
 * Page markup changes over time and is not a documented API, so extraction uses
 * several strategies (data-test attributes, semantic headings, text heuristics)
 * and returns null when it cannot find a title and description. The user can
 * always fall back to pasting the job into the dashboard.
 */
import type { ExtractedJob } from "./types";

const clean = (s: string | null | undefined) => (s ?? "").replace(/\s+/g, " ").trim();

/** Text of an element with a space between child elements (textContent would merge "<li>a</li><li>b</li>" into "ab"). */
export function spacedText(el: Element | null | undefined): string {
  if (!el) return "";
  const parts: string[] = [];
  const walker = el.ownerDocument.createTreeWalker(el, 4 /* NodeFilter.SHOW_TEXT */);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const parent = n.parentElement?.tagName;
    if (parent === "SCRIPT" || parent === "STYLE" || parent === "NOSCRIPT") continue;
    if (n.nodeValue?.trim()) parts.push(n.nodeValue);
  }
  return clean(parts.join(" "));
}

function firstText(root: ParentNode, selectors: string[]): string {
  for (const sel of selectors) {
    const el = root.querySelector(sel);
    const t = clean(el?.textContent);
    if (t) return t;
  }
  return "";
}

function multilineText(el: Element | null): string {
  if (!el) return "";
  const html = el as HTMLElement;
  const raw = typeof html.innerText === "string" && html.innerText.trim() ? html.innerText : (el.textContent ?? "");
  return raw
    .split("\n")
    .map((l) => l.replace(/\s+/g, " ").trim())
    .filter(Boolean)
    .join("\n")
    .trim();
}

function findDescription(doc: Document): string {
  const candidates = [
    '[data-test="Description"]',
    '[data-test="job-description-text"]',
    '[data-test="Description"] p',
    "section.job-description",
    '[itemprop="description"]',
  ];
  for (const sel of candidates) {
    const t = multilineText(doc.querySelector(sel));
    if (t.length >= 40) return t;
  }
  // Heading-based fallback: text following a "Summary"/"Description" heading.
  for (const h of Array.from(doc.querySelectorAll("h2, h3, h4, strong"))) {
    if (/^(summary|job description|description)$/i.test(clean(h.textContent))) {
      const container = h.closest("section") ?? h.parentElement;
      const t = multilineText(container).replace(/^(summary|job description|description)\s*/i, "");
      if (t.length >= 40) return t;
    }
  }
  return "";
}

function findSkills(doc: Document): string[] {
  const sels = [
    '[data-test="Skill"]',
    '[data-test="token"]',
    ".air3-token",
    '[data-test="skills"] a',
    '[data-test="skills"] span',
    ".skills-list li",
  ];
  const out: string[] = [];
  for (const sel of sels) {
    for (const el of Array.from(doc.querySelectorAll(sel))) {
      const t = clean(el.textContent);
      if (t && t.length <= 60 && !/^\+\d+$/.test(t) && !out.some((x) => x.toLowerCase() === t.toLowerCase())) out.push(t);
    }
    if (out.length) break;
  }
  return out.slice(0, 40);
}

const num = (s: string) => {
  const n = s.replace(/[,$\s]/g, "");
  return /^\d+(\.\d{1,2})?$/.test(n) ? n : null;
};

export function parseBudget(text: string): Pick<ExtractedJob, "budget_min" | "budget_max" | "job_type"> {
  const t = text.replace(/ /g, " ");
  const range = t.match(/\$\s?([\d,]+(?:\.\d{1,2})?)\s*[-–]\s*\$\s?([\d,]+(?:\.\d{1,2})?)\s*(?:\/\s*hr|\/hour|hourly|per hour)?/i);
  if (range && /hourly|\/\s*hr|per hour|\/hour/i.test(t)) {
    return { job_type: "hourly", budget_min: num(range[1]), budget_max: num(range[2]) };
  }
  const fixed = t.match(/(?:fixed[- ]price|budget)[^$]{0,40}\$\s?([\d,]+(?:\.\d{1,2})?)/i) ?? t.match(/\$\s?([\d,]+(?:\.\d{1,2})?)\s*(?:fixed[- ]price)/i);
  if (fixed) return { job_type: "fixed", budget_min: null, budget_max: num(fixed[1]) };
  if (/hourly/i.test(t)) return { job_type: "hourly", budget_min: range ? num(range[1]) : null, budget_max: range ? num(range[2]) : null };
  return { job_type: "unknown", budget_min: null, budget_max: null };
}

function findExperience(text: string): ExtractedJob["experience_level"] {
  const m = text.match(/\b(entry level|entry|intermediate|expert)\b\s*(?:level)?/i);
  if (!m) return "unknown";
  const v = m[1].toLowerCase();
  return v.startsWith("entry") ? "entry" : (v as ExtractedJob["experience_level"]);
}

function findClient(doc: Document, text: string): ExtractedJob["client_info"] {
  const info: NonNullable<ExtractedJob["client_info"]> = {};
  if (/payment method verified/i.test(text)) info.payment_verified = true;
  else if (/payment (method )?(not |un)verified/i.test(text)) info.payment_verified = false;
  const rating = text.match(/rating is ([0-5](?:\.\d+)?) out of 5/i) ?? text.match(/\b([0-5]\.\d{1,2}) of \d+ reviews/i);
  if (rating) info.rating = Number(rating[1]);
  const country = firstText(doc, ['[data-qa="client-location"] strong', '[data-test="LocationLabel"]']);
  if (country) info.country = country.slice(0, 100);
  return Object.keys(info).length ? info : null;
}

export function canonicalJobUrl(href: string): string | null {
  try {
    const u = new URL(href);
    if (u.protocol !== "https:") return null;
    return `${u.origin}${u.pathname}`;
  } catch {
    return null;
  }
}

export function extractJob(doc: Document, href: string): ExtractedJob | null {
  const title = firstText(doc, ['[data-test="job-title"]', "h1", 'header h4[data-test="title"]', "h2"]).slice(0, 300);
  const description = findDescription(doc).slice(0, 20000);
  if (title.length < 3 || description.length < 20) return null;

  const budgetText = [
    firstText(doc, ['[data-test="BudgetAmount"]', '[data-test="budget"]', '[data-test="job-type-label"]']),
    spacedText(doc.querySelector('[data-test="Features"], [data-test="about-job"], ul.features')),
  ].join(" ");
  const body = spacedText(doc.querySelector("body") ?? doc.documentElement).slice(0, 50000);
  const budget = parseBudget(budgetText.trim() || body);
  const proposals = body.match(/Proposals:\s*(Less than \d+|\d+\s*to\s*\d+|\d+\+)/i);

  return {
    title,
    description,
    url: canonicalJobUrl(href),
    ...budget,
    currency: "USD",
    required_skills: findSkills(doc),
    experience_level: findExperience(budgetText + " " + body.slice(0, 5000)),
    client_info: findClient(doc, body),
    proposals_info: proposals ? clean(proposals[1]).slice(0, 200) : null,
  };
}
