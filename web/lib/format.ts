import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { ValueKind } from "./types";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/**
 * Axis tick labels only. Reported amounts shown as text always come from the
 * server's presentation mapping (ADR 0006); ticks are a scale, not a fact.
 */
export function axisTick(value: number, kind: ValueKind): string {
  if (!Number.isFinite(value)) return "";
  if (kind === "percent") return `${Number((value * 100).toFixed(1))}%`;
  if (kind === "multiple") return `${value.toFixed(1)}x`;
  if (kind === "per_share") return `${value < 0 ? "-" : ""}$${Math.abs(value).toFixed(2)}`;
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);
  const scaled = (divisor: number, suffix: string) => {
    const n = abs / divisor;
    const digits = n >= 100 ? 0 : n >= 10 ? 1 : 2;
    return `${sign}$${Number(n.toFixed(digits))}${suffix}`;
  };
  if (abs >= 1e12) return scaled(1e12, "T");
  if (abs >= 1e9) return scaled(1e9, "B");
  if (abs >= 1e6) return scaled(1e6, "M");
  if (abs >= 1e3) return scaled(1e3, "K");
  return `${sign}$${abs.toFixed(0)}`;
}

/**
 * Trace values keep their line breaks: Markdown joins single newlines into one
 * line, so each becomes a hard break. Blank lines still separate paragraphs.
 */
export function hardBreaks(text: string): string {
  return text.replace(/([^\n])\n(?=[^\n])/g, "$1  \n");
}

const MD_LINK = /^\[([^\]]+)\]\(([^)]+)\)$/;

/** Trace values arrive as plain text or a single markdown link. */
export function parseLink(value: string): { text: string; href: string } | null {
  const match = MD_LINK.exec(value);
  if (!match) return null;
  const [, text, href] = match;
  return safeHref(href) ? { text, href } : null;
}

export function safeHref(href: string): boolean {
  try {
    const url = new URL(href);
    return url.protocol === "https:" || url.protocol === "http:";
  } catch {
    return false;
  }
}

/** "Live runtime — detail" → ["Live runtime", "detail"]; a banner without a dash stays whole. */
export function splitBanner(banner: string): [string, string] {
  const at = banner.indexOf(" — ");
  if (at < 0) return [banner, ""];
  return [banner.slice(0, at), banner.slice(at + 3)];
}

/** A filing named by whose it is and its accession: "Apple Inc., 10-Q 0000320193-26-000013". */
export function filingLabel(company: string, form: string, accession: string): string {
  return [company, [form, accession].filter(Boolean).join(" ")].filter(Boolean).join(", ");
}

/** A filing's address without the passage it points into (#:~:text=), or null if unsafe. */
export function filingUrl(url: string): string | null {
  if (!safeHref(url)) return null;
  const filing = new URL(url);
  filing.hash = "";
  return filing.href;
}
