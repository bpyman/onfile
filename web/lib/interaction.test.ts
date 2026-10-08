import { describe, expect, it } from "vitest";
import { barTicks } from "./chart-data";
import { changedSentences, isWordingOnly, orderChanges, splitChanges } from "./diff-view";
import { inspectorOrder } from "./inspect";
import { emphasis, toggleSeries, type LegendState } from "./legend";
import { pivotTable } from "./pivot";
import { shortcutFor } from "./shortcuts";
import { SERIES } from "./test-tables";
import type { DisplayDisclosure } from "./types";
import { wordDiff } from "./word-diff";

describe("legend state", () => {
  const all = ["s0", "s1", "s2"];
  const none: LegendState = { hidden: [], focus: null };

  it("toggles a series, but never hides the last one shown", () => {
    const one = toggleSeries(none, "s1", all);
    expect(one.hidden).toEqual(["s1"]);
    expect(toggleSeries(one, "s1", all).hidden).toEqual([]);
    const two = toggleSeries(toggleSeries(none, "s0", all), "s1", all);
    expect(toggleSeries(two, "s2", all).hidden).toEqual(["s0", "s1"]);
  });

  it("highlights the focused series and dims the rest", () => {
    const focused: LegendState = { hidden: ["s2"], focus: "s1" };
    expect(emphasis(focused, "s1")).toBe("focus");
    expect(emphasis(focused, "s0")).toBe("dim");
    expect(emphasis(focused, "s2")).toBe("hidden");
    expect(emphasis(none, "s0")).toBe("normal");
  });
});

describe("inspectorOrder", () => {
  it("lists sources as the table shows them, then the facts behind them", () => {
    const pivot = pivotTable(SERIES);
    if (!pivot) throw new Error("no pivot");
    // Rows sorted oldest first: Sep (5, 9), Dec (4, 8), Mar (3, 7), Jun (0, 6).
    expect(inspectorOrder(10, pivot, [3, 2, 1, 0])).toEqual([5, 9, 4, 8, 3, 7, 0, 6, 1, 2]);
    expect(inspectorOrder(3, null, null)).toEqual([0, 1, 2]);
  });
});

describe("pivotTable", () => {
  it("reads quarters across when the companies' quarters end within a week", () => {
    const pivot = pivotTable(SERIES);
    expect(pivot?.rows.map((row) => row.slice(1).every(Boolean))).toEqual([true, true, true, true]);
  });

  it("keeps the table when fiscal calendars differ, rather than half-empty rows", () => {
    // NVIDIA's quarters end in late July, Apple's in late June: a month apart.
    const offset = {
      ...SERIES,
      rows: SERIES.rows.map((row, index) => (index < 4 ? ["NVIDIA Corporation", "NVDA", ...row.slice(2)] : row)),
      numbers: SERIES.numbers.map((row, index) => (index < 4 ? [null, null, row[2], (row[3] as number) + 26] : row)),
    };
    expect(pivotTable(offset)).toBeNull();
  });

  it("shows a repeated company and quarter once", () => {
    const repeated = {
      ...SERIES,
      rows: [...SERIES.rows, SERIES.rows[0]],
      numbers: [...SERIES.numbers, SERIES.numbers[0]],
      row_keys: [...(SERIES.row_keys ?? []), "MSFT@2026-06-30"],
      evidence: [...(SERIES.evidence ?? []), [null, null, 0, null]],
      raw: SERIES.raw ? [...SERIES.raw, SERIES.raw[0]] : undefined,
    };
    expect(pivotTable(repeated)?.rows).toHaveLength(4);
  });
});

describe("barTicks", () => {
  it("stops at the first nice tick above the largest bar", () => {
    const ticks = barTicks([18.2e9, 5e9, null]);
    expect(ticks[0]).toBe(0);
    expect(ticks[ticks.length - 1]).toBe(20e9);
    expect(barTicks([-8, 12])[0]).toBeLessThanOrEqual(-8);
    expect(barTicks([]).length).toBeGreaterThan(1);
  });
});

describe("shortcutFor", () => {
  const key = (init: Partial<{ key: string; target: string; editable: boolean; modifier: boolean }>) => ({
    key: init.key ?? "/",
    targetTag: init.target ?? "BODY",
    editable: init.editable ?? false,
    modifier: init.modifier ?? false,
  });

  it("takes / to the question box unless typing somewhere", () => {
    expect(shortcutFor(key({}))).toBe("focus-composer");
    expect(shortcutFor(key({ target: "INPUT" }))).toBeNull();
    expect(shortcutFor(key({ target: "TEXTAREA" }))).toBeNull();
    expect(shortcutFor(key({ editable: true }))).toBeNull();
    expect(shortcutFor(key({ modifier: true }))).toBeNull();
    expect(shortcutFor(key({ key: "a" }))).toBeNull();
  });
});

function change(kind: string, before: string, after: string): DisplayDisclosure {
  return {
    section_label: "MD&A",
    change_kind: kind,
    before_text: before,
    after_text: after,
    older_accession: "a",
    newer_accession: "b",
    older_url: "",
    newer_url: "",
  };
}

describe("filing change order", () => {
  const wording = change("changed", "We may expand our offerings.", "We could expand our offerings.");
  const small = change("changed", "Revenue was $10 billion.", "Revenue was $12 billion.");
  const big = change(
    "changed",
    "Revenue was $10 billion and margin 40%. Costs rose.",
    "Revenue was $14 billion and margin 44%. Costs fell sharply this quarter.",
  );
  const added = change("added", "", "A new risk about tariffs.");

  it("puts numeric changes first in the filing's order, and folds wording-only edits", () => {
    expect(isWordingOnly(wording)).toBe(true);
    expect(isWordingOnly(small)).toBe(false);
    expect(isWordingOnly(added)).toBe(false);
    // A filing leads with its headline figures; a longer edit does not outrank them.
    expect(orderChanges([wording, added, small, big])).toEqual([small, big, added, wording]);
  });

  it("splits the ordered changes into those worth showing and the rewordings folded away", () => {
    expect(splitChanges([wording, added, small, big])).toEqual({ substantive: [small, big, added], wording: [wording] });
    expect(splitChanges([added])).toEqual({ substantive: [added], wording: [] });
  });

  it("puts a changed figure ahead of a whole paragraph added or removed with figures in it", () => {
    // A removed bullet holds figures, but "20% to 29%" says more than a paragraph gone.
    const removed = change("removed", "Segment revenue increased 11% driven by cloud growth of 12%.", "");
    expect(orderChanges([removed, added, small])).toEqual([small, removed, added]);
  });

  it("reads a reworded paragraph whose dates rolled forward as a rewording", () => {
    const rolled = change(
      "changed",
      "As of March 31, 2026, we expect results in fiscal 2026 to be affected.",
      "As of June 30, 2026, we now expect results in fiscal 2027 to be affected.",
    );
    const moved = change(
      "changed",
      "As of March 31, 2026, revenue grew 12%.",
      "As of June 30, 2026, revenue grew 15%.",
    );
    expect(isWordingOnly(rolled)).toBe(true);
    expect(isWordingOnly(moved)).toBe(false);
  });

  it("clamps a paragraph to the sentences that changed", () => {
    const diff = wordDiff(
      "Intro sentence stays. Revenue was $10 billion. Closing words stay.",
      "Intro sentence stays. Revenue was $12 billion. Closing words stay.",
    );
    if (!diff) throw new Error("no diff");
    const { sentences, omitted } = changedSentences(diff.unified);
    expect(omitted).toBe(true);
    expect(sentences).toHaveLength(1);
    expect(sentences[0].map((piece) => piece.text).join("")).toContain("Revenue was");
    expect(sentences[0].some((piece) => piece.kind === "removed" && piece.text.includes("$10"))).toBe(true);
  });
});
