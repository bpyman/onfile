import { describe, expect, it } from "vitest";
import { clarifyChoices, shownMessage, slugNote } from "./clarify";
import type { Presentation, Turn } from "./types";

function turn(index: number, message: string, slugs: string[] = [], labels: string[] = []): Turn {
  const presentation = { candidates: labels } as unknown as Presentation;
  return { index, message, presentation, candidate_slugs: slugs, clarify_enabled: false };
}

// Shape captured from "What was Google's latest quarterly profit?" on the recorded runtime.
const ASKED = turn(
  0,
  "What was Google's latest quarterly profit?",
  ["gross_profit", "operating_income", "net_income"],
  ["Gross profit", "Operating income", "Net income"],
);

describe("clarifyChoices", () => {
  it("pairs each catalog slug with its label", () => {
    expect(clarifyChoices(ASKED)).toEqual([
      { slug: "gross_profit", label: "Gross profit", chosen: false },
      { slug: "operating_income", label: "Operating income", chosen: false },
      { slug: "net_income", label: "Net income", chosen: false },
    ]);
  });

  it("marks the candidate the next message answered with", () => {
    const chosen = clarifyChoices(ASKED, turn(1, "net_income")).filter((choice) => choice.chosen);
    expect(chosen.map((choice) => choice.slug)).toEqual(["net_income"]);
  });

  it("accepts a typed label as the answer", () => {
    const chosen = clarifyChoices(ASKED, turn(1, " Operating Income ")).filter((choice) => choice.chosen);
    expect(chosen.map((choice) => choice.slug)).toEqual(["operating_income"]);
  });

  it("marks nothing when the analyst moved on", () => {
    expect(clarifyChoices(ASKED, turn(1, "add Apple")).some((choice) => choice.chosen)).toBe(false);
  });

  it("falls back to the slug when a label is missing", () => {
    expect(clarifyChoices(turn(0, "compare to last year", ["extend", "replace"], ["Extend"]))).toEqual([
      { slug: "extend", label: "Extend", chosen: false },
      { slug: "replace", label: "replace", chosen: false },
    ]);
  });

  it("falls back to the slug's words, never its underscores", () => {
    expect(clarifyChoices(turn(0, "margin", ["year_over_year"], []))[0].label).toBe("year over year");
  });
});

describe("shownMessage", () => {
  it("shows a clarify answer by its label", () => {
    expect(shownMessage(turn(1, "net_income"), ASKED)).toBe("Net income");
  });

  it("keeps any other message as sent", () => {
    expect(shownMessage(turn(1, "add Apple"), ASKED)).toBe("add Apple");
    expect(shownMessage(turn(0, "net_income"))).toBe("net_income");
  });
});

describe("slugNote", () => {
  it("is empty when the label already says the slug's words", () => {
    expect(slugNote("year_over_year", "The same quarter a year earlier (year over year)")).toBeNull();
    expect(slugNote("sequential", "The quarter before (sequential)")).toBeNull();
    expect(slugNote("net_income", "Net income")).toBeNull();
    expect(slugNote("KO", "Coca-Cola Co (KO)")).toBeNull();
  });

  it("ignores punctuation the label adds", () => {
    expect(slugNote("shareholders_equity", "Shareholders' equity")).toBeNull();
    expect(slugNote("selling_general_and_administrative", "Selling, general and administrative")).toBeNull();
  });

  it("gives the slug as words when the label reads differently", () => {
    expect(slugNote("eps_diluted", "Diluted EPS")).toBe("eps diluted");
  });
});
