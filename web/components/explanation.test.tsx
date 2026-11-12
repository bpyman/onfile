import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { DisplayExplanation } from "@/lib/types";
import { ManagementExplanation, readable } from "./explanation";

describe("readable", () => {
  it("drops a list bullet the filing left at a paragraph's start, and nothing else", () => {
    expect(readable("•Cost of revenues was $45.9 billion")).toBe("Cost of revenues was $45.9 billion");
    expect(readable("• Revenue rose")).toBe("Revenue rose");
    expect(readable("-$5 million of charges")).toBe("-$5 million of charges");
    expect(readable("Revenue rose • strongly")).toBe("Revenue rose • strongly");
  });
});

const FILING = "https://www.sec.gov/Archives/edgar/data/1652044/000165204426000071/goog-20260630.htm";

const explained: DisplayExplanation = {
  heading: "Management's explanation",
  note: null,
  companies: [
    {
      company_name: "Alphabet Inc.",
      source: "From Alphabet's 10-Q for the quarter ended Jun 30, 2026 · MD&A",
      filing_url: FILING,
      mda_url: `${FILING}#:~:text=Overview`,
      explanation: 'Cost of revenues rose, "driven by increases in depreciation expense".',
      paragraphs: [
        {
          text: "Cost of revenues increased, driven by increases in depreciation expense.",
          url: `${FILING}#:~:text=Cost%20of%20revenues%20increased`,
        },
        { text: "Other costs rose on content acquisition.", url: `${FILING}#:~:text=Other%20costs` },
      ],
      unavailable: null,
    },
  ],
};

const render = (explanation: DisplayExplanation) =>
  renderToStaticMarkup(createElement(ManagementExplanation, { explanation }));

describe("ManagementExplanation", () => {
  it("heads the panel and names the 10-Q, linking its MD&A", () => {
    const html = render(explained);
    expect(html).toContain("Management&#x27;s explanation");
    expect(html).toContain("From Alphabet&#x27;s 10-Q for the quarter ended Jun 30, 2026");
    expect(html).toContain(`href="${FILING}#:~:text=Overview"`);
  });

  it("marks the explanation as the model's, then quotes each paragraph with its link", () => {
    const html = render(explained);
    expect(html).toContain("Written by the model from the quoted paragraphs");
    expect(html).toContain("driven by increases in depreciation expense");
    expect(html.match(/<blockquote/g)).toHaveLength(2);
    expect(html.match(/Read in the filing/g)).toHaveLength(2);
    expect(html).toContain(`href="${FILING}#:~:text=Cost%20of%20revenues%20increased"`);
    // The model's explanation comes before the paragraphs it was drawn from.
    expect(html.indexOf("Written by the model")).toBeLessThan(html.indexOf("<blockquote"));
  });

  it("folds the paragraphs behind a button on a phone", () => {
    const html = render(explained);
    expect(html).toContain("Show the paragraphs");
    expect(html).toMatch(/aria-expanded="false"[^>]*>[^<]*<[^>]*>?[^]*?Show the paragraphs/);
    expect(html).toMatch(/class="[^"]*hidden[^"]*sm:block[^"]*"/);
  });

  it("says what happened instead, with a link to the MD&A", () => {
    const html = render({
      ...explained,
      note: "This 10-Q explains the change against a year earlier, not the quarter before",
      companies: [
        {
          ...explained.companies[0],
          explanation: "",
          paragraphs: [],
          unavailable: "I couldn't find management's explanation in this 10-Q",
        },
      ],
    });
    expect(html).toContain("I couldn&#x27;t find management&#x27;s explanation in this 10-Q.");
    expect(html).toContain("Read the MD&amp;A");
    expect(html).toContain("not the quarter before");
    expect(html).not.toContain("<blockquote");
    expect(html).not.toContain("Show the paragraphs");
    expect(html).not.toContain("Written by the model");
  });

  it("shows each company of a comparison", () => {
    const amgen = {
      ...explained.companies[0],
      company_name: "Amgen Inc.",
      source: "From Amgen's 10-Q for the quarter ended Jun 30, 2026 · MD&A",
    };
    const html = render({ ...explained, companies: [...explained.companies, amgen] });
    expect(html).toContain("From Amgen&#x27;s 10-Q");
    expect(html).toContain("From Alphabet&#x27;s 10-Q");
  });

  it("drops a link that is not to the filing's site", () => {
    const html = render({
      ...explained,
      companies: [{ ...explained.companies[0], mda_url: "javascript:alert(1)" }],
    });
    expect(html).not.toContain("javascript:");
  });
});
