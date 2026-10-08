import { filingLabel, filingUrl } from "./format";
import type { Presentation } from "./types";

/**
 * Where an answer's notes go, so the answer reads first: a † derivation note
 * is a footnote under the figures, the snapshot's timestamp joins the caption,
 * and the rest (period and ordering notes) is one compact line. The text is
 * the server's; only its place changes.
 */
export interface AnswerNotes {
  footnotes: string[];
  snapshot: string | null;
  notes: string[];
}

const SNAPSHOT = "Universe snapshot as of ";

/** What the snapshot's timestamp means, shown where the timestamp is. */
export const SNAPSHOT_HELP =
  "The universe snapshot is a dated list of US-listed operating companies with their market caps. Rankings read it; it is not rescreened live.";

export function splitNotes(banners: string[]): AnswerNotes {
  const split: AnswerNotes = { footnotes: [], snapshot: null, notes: [] };
  for (const banner of banners) {
    if (banner.startsWith("†")) split.footnotes.push(banner);
    else if (banner.startsWith(SNAPSHOT) && split.snapshot === null) split.snapshot = banner;
    else split.notes.push(banner);
  }
  return split;
}

export interface FilingLink {
  url: string;
  label: string;
}

/** Where a filing an answer read was cited: a fact card, an evidence item, or one side of a change. */
export interface FilingSource {
  url: string;
  company: string;
  form: string;
  accession: string;
  /** What to call the filing when it has no company, form or accession. */
  fallback: string;
  /** Set for a change's two filings, which have no company or form of their own. */
  side?: "older" | "newer";
}

/**
 * Each filing the answer read, once, in citing order, labelled by the caller.
 * A link into a passage (#:~:text=) is still the same filing; the first
 * citation names it.
 */
export function eachFiling(presentation: Presentation, label: (source: FilingSource) => string): FilingLink[] {
  const seen = new Map<string, string>();
  const add = (source: FilingSource) => {
    const filing = filingUrl(source.url);
    if (filing === null || seen.has(filing)) return;
    seen.set(filing, label(source));
  };
  const card = presentation.fact_card;
  if (card) {
    add({
      url: card.source_url,
      company: card.company_name,
      form: card.form,
      accession: card.accession_number,
      fallback: card.metric_header,
    });
  }
  for (const item of presentation.evidence) {
    add({
      url: item.source_url,
      company: item.company_name,
      form: item.form,
      accession: item.accession_number,
      fallback: item.label,
    });
  }
  for (const change of presentation.disclosures) {
    add({
      url: change.older_url,
      company: "",
      form: "",
      accession: change.older_accession,
      fallback: `Older filing ${change.older_accession}`,
      side: "older",
    });
    add({
      url: change.newer_url,
      company: "",
      form: "",
      accession: change.newer_accession,
      fallback: `Newer filing ${change.newer_accession}`,
      side: "newer",
    });
  }
  return [...seen].map(([url, label]) => ({ url, label }));
}

const SIDE_NAMES = { older: "Previous filing", newer: "Current filing" } as const;

/** Each filing the answer read, named for the window's Sources list. */
export function answerFilings(presentation: Presentation): FilingLink[] {
  return eachFiling(
    presentation,
    ({ url, company, form, accession, side }) =>
      filingLabel(side ? SIDE_NAMES[side] : company, form, accession) || new URL(url).hostname,
  );
}
