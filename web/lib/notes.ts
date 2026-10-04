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

/** Each filing the answer read, once: a link into a passage (#:~:text=) is still the same filing. */
export function answerFilings(presentation: Presentation): FilingLink[] {
  const seen = new Map<string, string>();
  const add = (url: string, company: string, form: string, accession: string) => {
    const filing = filingUrl(url);
    if (filing === null || seen.has(filing)) return;
    seen.set(filing, filingLabel(company, form, accession) || new URL(filing).hostname);
  };
  const card = presentation.fact_card;
  if (card) add(card.source_url, card.company_name, card.form, card.accession_number);
  for (const item of presentation.evidence) add(item.source_url, item.company_name, item.form, item.accession_number);
  for (const change of presentation.disclosures) {
    add(change.older_url, "Previous filing", "", change.older_accession);
    add(change.newer_url, "Current filing", "", change.newer_accession);
  }
  return [...seen].map(([url, label]) => ({ url, label }));
}
