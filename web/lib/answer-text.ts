import { filingLabel, filingUrl, safeHref } from "./format";
import type { DisplayTable, Presentation } from "./types";

/**
 * An answer as Markdown, for copying into a note or saving: the question, what
 * the window shows, and every source it cites, so the copy carries its own
 * provenance. Every amount is the server's string (ADR 0006); only layout is
 * added here. Text the window shows as text stays text: it is escaped, and the
 * essay keeps only the links the window would draw.
 */
export function answerMarkdown(
  question: string,
  presentation: Presentation,
  /** The table's rows in the order on screen; the server's order when absent. */
  rowOrder?: number[] | null,
  /** The table as on screen (several companies' quarters turned to read across). */
  shown?: DisplayTable | null,
): string {
  const blocks: string[] = [];
  if (question.trim()) blocks.push(`## ${plain(question)}`);
  if (presentation.headline) blocks.push(plain(presentation.headline));
  for (const banner of presentation.banners) blocks.push(`> ${plain(banner)}`);

  const card = presentation.fact_card;
  if (card) {
    const company = card.ticker ? `${card.company_name} (${card.ticker})` : card.company_name;
    const lines = [`**${plain(`${card.metric_header}, ${company}: ${card.amount}`)}**`, plain(card.period_label)];
    const filed = [card.form, card.accession_number && `accession ${card.accession_number}`].filter(Boolean).map(plain);
    if (filed.length) lines.push(`Filed in ${filed.join(", ")}`);
    blocks.push(lines.filter(Boolean).join("  \n"));
  }

  for (const trend of presentation.trends) {
    const name = trend.series[0] ?? "";
    const points = trend.period_labels.map((period, index) => `${period}: ${trend.amounts[index]?.[name] ?? "—"}`);
    blocks.push(`**${plain(trend.metric_label)}, recent quarters:** ${plain(points.join(" · "))}`);
  }

  const table = shown ?? presentation.table;
  if (table && table.rows.length > 0) blocks.push(markdownTable(table, rowOrder));
  if (presentation.chart?.caption) blocks.push(`_${plain(presentation.chart.caption)}_`);
  if (presentation.message) blocks.push(plain(presentation.message));
  if (presentation.essay) {
    const cited = presentation.citations.map((citation) => citation.url).filter(safeHref);
    blocks.push(safeEssay(presentation.essay, cited));
  }

  for (const change of presentation.disclosures) {
    const heading = [change.section_label, change.subsection].filter(Boolean).join(": ");
    const lines = [`### ${plain(heading)} (${plain(change.change_kind)})`];
    if (change.before_text) lines.push(`Before:\n${quote(change.before_text)}`);
    if (change.after_text) lines.push(`After:\n${quote(change.after_text)}`);
    blocks.push(lines.join("\n\n"));
  }

  const citations = presentation.citations.map((citation) => {
    const title = plain(citation.title) || plain(citation.url);
    const link = safeHref(citation.url) ? `[${title}](${destination(citation.url)})` : title;
    return `${citation.index}. ${link}${citation.published ? `, ${plain(citation.published)}` : ""}`;
  });
  if (citations.length) blocks.push(`**Sources**\n\n${citations.join("\n")}`);

  const filings = filingLinks(presentation);
  if (filings.length) blocks.push(`**SEC filings**\n\n${filings.join("\n")}`);
  return `${blocks.join("\n\n")}\n`;
}

/** A file name for the saved answer: the question's words, or "answer". */
export function answerFileName(question: string): string {
  const slug = question
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60)
    .replace(/-+$/, "");
  return `${slug || "answer"}.md`;
}

function markdownTable(table: DisplayTable, rowOrder?: number[] | null): string {
  const order = rowOrder ?? table.rows.map((_, index) => index);
  const line = (cells: string[]) => `| ${cells.map(cell).join(" | ")} |`;
  return [
    line(table.headers),
    line(table.headers.map(() => "---")),
    ...order.map((row) => line(table.rows[row] ?? [])),
  ].join("\n");
}

function cell(text: string): string {
  return plain(text) || " ";
}

function oneLine(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

/**
 * Text as the window shows it, so Markdown reads it the same: characters that
 * would start markup (emphasis, a link, a heading, HTML, a table cell) are
 * escaped, and so is a line start that would make a list.
 */
function escaped(text: string): string {
  return text
    .replace(/[\\`*_[\]<>|~#]/g, "\\$&")
    .replace(/^(\s*)([-+]|\d+[.)])(?=\s|$)/gm, (_, space: string, marker: string) =>
      `${space}${marker.replace(/[-+.)]$/, "\\$&")}`,
    );
}

/** One line of escaped text. */
function plain(text: string): string {
  return escaped(oneLine(text));
}

/**
 * A link destination that cannot end early: the URL in its canonical form,
 * with the characters Markdown reads as its end percent-encoded.
 */
function destination(url: string): string {
  return new URL(url).href.replace(
    /[()<>\s]/g,
    (char) => `%${char.charCodeAt(0).toString(16).toUpperCase().padStart(2, "0")}`,
  );
}

function quote(text: string): string {
  return text
    .trim()
    .split("\n")
    .map((line) => `> ${escaped(line)}`.trimEnd())
    .join("\n");
}

/** "](dest)" or "](<dest> "title")", the destination one level of parentheses deep. */
const LINK_DESTINATION = /\]\(\s*<?((?:[^()\s<>]|\([^()\s]*\))*)>?(?:\s+"[^"]*")?\s*\)/g;

/**
 * The essay under the window's rules (components/markdown.tsx): raw HTML is
 * dropped, an image is its alt text, and only a link to a cited source stays a
 * link; any other link is its text.
 */
export function safeEssay(essay: string, cited: string[]): string {
  return essay
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/<\/?[A-Za-z][^>]*>/g, "")
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/^\s*\[[^\]]+\]:\s*\S+.*$/gm, "")
    .replace(/\[([^\]]*)\]\(\s*<?([^)\s>]*)>?(?:\s+"[^"]*")?\s*\)/g, (_, text: string, href: string) =>
      safeHref(href) && cited.includes(href) ? `[${text}](${destination(href)})` : text,
    )
    .replace(/<(https?:\/\/[^>\s]+)>/g, "$1")
    // Any link the pass above could not read ("[a [b] c](javascript:…)": its
    // text holds a bracket) loses its destination unless that is a cited source.
    .replace(LINK_DESTINATION, (whole: string, href: string) =>
      safeHref(href) && (cited.includes(href) || cited.some((url) => destination(url) === href))
        ? whole
        : "]",
    )
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}


/**
 * Each filing the answer read, once, with what was taken from it. A link into
 * a passage (#:~:text=) is still the same filing.
 */
function filingLinks(presentation: Presentation): string[] {
  const seen = new Map<string, string>();
  const add = (url: string, label: string) => {
    const filing = filingUrl(url);
    if (filing !== null && !seen.has(filing)) seen.set(filing, plain(label));
  };
  // A filing is named by whose it is and its accession; several figures often share one.
  const filing = (company: string, form: string, accession: string, fallback: string) =>
    filingLabel(company, form, accession) || fallback;
  const card = presentation.fact_card;
  if (card) add(card.source_url, filing(card.company_name, card.form, card.accession_number, card.metric_header));
  for (const item of presentation.evidence) {
    add(item.source_url, filing(item.company_name, item.form, item.accession_number, item.label));
  }
  for (const change of presentation.disclosures) {
    add(change.older_url, `Older filing ${change.older_accession}`);
    add(change.newer_url, `Newer filing ${change.newer_accession}`);
  }
  return [...seen].map(([url, label]) => `- [${label || plain(url)}](${destination(url)})`);
}
