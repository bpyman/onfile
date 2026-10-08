import type { DisplayDisclosure } from "./types";
import type { UnifiedPiece } from "./word-diff";

/**
 * How the 10-Q changes are laid out: what moved a number first, in the filing's
 * order, then other edits larger before smaller, and edits that only reword
 * folded away. The text itself is the filing's, untouched.
 */

const FIGURE = /\$?\d[\d,]*(?:\.\d+)?%?/g;
const MONTH =
  "(?:January|February|March|April|May|June|July|August|September|October|November|December" +
  "|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\\.?";
// Dates, years and page references move from one filing to the next without the
// disclosure changing; the server masks the same ones (filing_change._DATES).
const DATES = new RegExp(
  `\\b${MONTH}\\s+\\d{1,2},?\\s+(?:19|20)\\d{2}(?!\\d)` +
    "|(?<!\\d)(?:19|20)\\d{2}(?!\\d)" +
    "|\\bpages?\\s+\\d{1,3}(?:\\s*[-–]\\s*\\d{1,3})?\\b",
  "gi",
);

function figures(text: string): string[] {
  return (text.replace(DATES, " ").match(FIGURE) ?? []).sort();
}

/** Whether a changed paragraph's figures differ, not only its words. */
export function changesFigures(item: DisplayDisclosure): boolean {
  const before = figures(item.before_text);
  const after = figures(item.after_text);
  return before.length !== after.length || before.some((figure, index) => figure !== after[index]);
}

/**
 * Where a change goes: a figure that moved within a paragraph (0), a paragraph
 * added, removed or otherwise edited (1), or a rewording (2).
 */
function rank(item: DisplayDisclosure): number {
  return item.change_kind !== "changed" ? 1 : changesFigures(item) ? 0 : 2;
}

/** A rewording: the paragraph changed, its figures did not. */
export function isWordingOnly(item: DisplayDisclosure): boolean {
  return rank(item) === 2;
}

/** How much changed, in words gone or come. */
function size(item: DisplayDisclosure): number {
  const words = (text: string) => new Set(text.split(/\s+/).filter(Boolean));
  const before = words(item.before_text);
  const after = words(item.after_text);
  let changed = 0;
  for (const word of before) if (!after.has(word)) changed += 1;
  for (const word of after) if (!before.has(word)) changed += 1;
  return changed;
}

/**
 * Figures that moved within a paragraph first, in the filing's order (it leads
 * with its headline figures); then additions, removals and other edits, larger
 * before smaller; then rewordings. A paragraph added or removed whole has
 * figures on one side only, but says less than "20% to 29%".
 */
export function orderChanges(items: DisplayDisclosure[]): DisplayDisclosure[] {
  return ranked(items).map(({ item }) => item);
}

/**
 * The changes in that order, split into those worth a row of their own and the
 * rewordings (the order's tail) that fold into one.
 */
export function splitChanges(items: DisplayDisclosure[]): {
  substantive: DisplayDisclosure[];
  wording: DisplayDisclosure[];
} {
  const ordered = ranked(items);
  const first = ordered.findIndex((entry) => entry.rank === 2);
  const tail = first < 0 ? ordered.length : first;
  return {
    substantive: ordered.slice(0, tail).map(({ item }) => item),
    wording: ordered.slice(tail).map(({ item }) => item),
  };
}

function ranked(items: DisplayDisclosure[]): { item: DisplayDisclosure; rank: number }[] {
  return items
    .map((item, index) => ({ item, index, rank: rank(item), size: size(item) }))
    .sort((a, b) => a.rank - b.rank || (a.rank === 1 ? b.size - a.size : 0) || a.index - b.index);
}

// A sentence ends at . ! or ? followed by space and a capital or an opening mark.
const SENTENCE_END = /([.!?]["”’)]?\s+)(?=[A-Z(“"'])/g;

/**
 * The sentences of a merged paragraph that hold a change, each as its runs;
 * `omitted` says sentences that read the same were left out.
 */
export function changedSentences(pieces: UnifiedPiece[]): { sentences: UnifiedPiece[][]; omitted: boolean } {
  const sentences: UnifiedPiece[][] = [[]];
  for (const piece of pieces) {
    if (piece.kind !== "same") {
      sentences[sentences.length - 1].push(piece);
      continue;
    }
    // Only kept text splits: a sentence break inside an edit stays with the edit.
    const parts = piece.text.split(SENTENCE_END);
    for (let index = 0; index < parts.length; index += 2) {
      const text = parts[index] + (parts[index + 1] ?? "");
      if (text) sentences[sentences.length - 1].push({ text, kind: "same" });
      if (parts[index + 1] !== undefined) sentences.push([]);
    }
  }
  const kept = sentences.filter((sentence) => sentence.some((piece) => piece.kind !== "same"));
  return { sentences: kept, omitted: kept.length < sentences.filter((sentence) => sentence.length).length };
}
