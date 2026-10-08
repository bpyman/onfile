import { describe, expect, it } from "vitest";
import { answerFilings, eachFiling, splitNotes } from "./notes";
import type { Presentation } from "./types";

describe("splitNotes", () => {
  it("puts the † note under the figures, the snapshot in the caption, and the rest on one line", () => {
    const split = splitNotes([
      "Universe snapshot as of Sep 27, 2026, 10:43 PM UTC",
      "† Derived from reported figures because the filings do not report it on its own.",
      "Filings report quarters, not months or weeks, so this shows the latest quarter.",
    ]);
    expect(split.snapshot).toBe("Universe snapshot as of Sep 27, 2026, 10:43 PM UTC");
    expect(split.footnotes).toEqual(["† Derived from reported figures because the filings do not report it on its own."]);
    expect(split.notes).toEqual(["Filings report quarters, not months or weeks, so this shows the latest quarter."]);
  });
});

describe("answerFilings", () => {
  it("lists each filing once, whatever passage a link points into", () => {
    const item = {
      label: "",
      amount: "",
      raw_amount: "",
      company_name: "Microsoft Corporation",
      ticker: "MSFT",
      cik: "",
      concept: "",
      period_label: "",
      accession_number: "0001193125-26-323660",
      form: "10-K",
      source_url: "https://www.sec.gov/a.htm#:~:text=Revenue",
      selection_rule: "",
    };
    const filings = answerFilings({
      fact_card: null,
      evidence: [item, { ...item, source_url: "https://www.sec.gov/a.htm" }, { ...item, source_url: "javascript:alert(1)" }],
      disclosures: [],
    } as unknown as Presentation);
    expect(filings).toEqual([
      { url: "https://www.sec.gov/a.htm", label: "Microsoft Corporation, 10-K 0001193125-26-323660" },
    ]);
  });
});

describe("eachFiling", () => {
  it("walks the card, the evidence and both sides of each change once, labelled by the caller", () => {
    const item = {
      label: "Revenue",
      amount: "",
      raw_amount: "",
      company_name: "Microsoft Corporation",
      ticker: "MSFT",
      cik: "",
      concept: "",
      period_label: "",
      accession_number: "0001193125-26-323660",
      form: "10-K",
      source_url: "https://www.sec.gov/a.htm#:~:text=Revenue",
      selection_rule: "",
    };
    const change = {
      section_label: "Risk Factors",
      change_kind: "changed",
      before_text: "",
      after_text: "",
      older_accession: "A-1",
      newer_accession: "A-2",
      older_url: "https://www.sec.gov/a1.htm#:~:text=One",
      newer_url: "https://www.sec.gov/a.htm#:~:text=Two",
    };
    const filings = eachFiling(
      {
        fact_card: { ...item, metric_header: "Net income", source_url: "javascript:alert(1)" },
        evidence: [item, { ...item, source_url: "https://www.sec.gov/a.htm", label: "Later" }],
        disclosures: [change],
      } as unknown as Presentation,
      (source) => `${source.side ?? source.company}|${source.form}|${source.accession}|${source.fallback}`,
    );
    expect(filings).toEqual([
      { url: "https://www.sec.gov/a.htm", label: "Microsoft Corporation|10-K|0001193125-26-323660|Revenue" },
      { url: "https://www.sec.gov/a1.htm", label: "older||A-1|Older filing A-1" },
    ]);
  });

  it("names a change's sides Previous and Current filing for the window, as before", () => {
    const filings = answerFilings({
      fact_card: null,
      evidence: [],
      disclosures: [
        {
          section_label: "",
          change_kind: "changed",
          before_text: "",
          after_text: "",
          older_accession: "A-1",
          newer_accession: "A-2",
          older_url: "https://www.sec.gov/a1.htm",
          newer_url: "https://www.sec.gov/a2.htm",
        },
      ],
    } as unknown as Presentation);
    expect(filings).toEqual([
      { url: "https://www.sec.gov/a1.htm", label: "Previous filing, A-1" },
      { url: "https://www.sec.gov/a2.htm", label: "Current filing, A-2" },
    ]);
  });
});
