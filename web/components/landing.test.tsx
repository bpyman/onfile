// @vitest-environment jsdom

import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Meta } from "../lib/types";
import { Landing } from "./landing";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// What /api/meta sends with news on (storefront.capabilities_for).
const CAPABILITIES: Meta["capabilities"] = [
  {
    description: "Look up any quarter's financials",
    examples: [
      "What was Microsoft's latest quarterly revenue?",
      "Apple diluted EPS in Q3 FY2025",
      "Microsoft free cash flow over the last four quarters",
      "How is Nvidia doing?",
    ],
  },
  { description: "Compare companies on metrics", examples: ["Compare Eli Lilly and Merck net margins"] },
  { description: "Access financial news", examples: ["What's going on with Eli Lilly's obesity drugs?"] },
  { description: "Answer general queries", examples: ["How could AI change bank underwriting?"] },
  {
    description: "Stay on the same thread",
    examples: ["add Apple", "now add operating margin", "make that the last four quarters", "show year-over-year"],
  },
];

const META = {
  guided_stories: [{ label: "Verify a quarterly fact", question: "What was Microsoft's latest quarterly pretax income?" }],
  capabilities: CAPABILITIES,
  metric_groups: [],
} as unknown as Meta;

let root: ReturnType<typeof createRoot> | null = null;
let container: HTMLElement;
const onDraft = vi.fn();

beforeEach(() => {
  // The hero preview loads only on a wide screen; jsdom has no matchMedia.
  vi.stubGlobal("matchMedia", () => ({ matches: false }));
  onDraft.mockClear();
  container = document.createElement("div");
  root = createRoot(container);
  act(() => {
    root!.render(
      createElement(Landing, {
        meta: META,
        waking: false,
        error: null,
        disabled: false,
        onAsk: vi.fn(),
        onDraft,
        onRetry: vi.fn(),
      }),
    );
  });
});

afterEach(() => {
  act(() => root?.unmount());
  root = null;
  vi.unstubAllGlobals();
});

const lines = () => [...container.querySelectorAll('[aria-labelledby="ask-label"] li > p')].map((p) => p.textContent);
const button = (name: string | RegExp) =>
  [...container.querySelectorAll("button")].find((b) =>
    typeof name === "string" ? (b.getAttribute("aria-label") ?? b.textContent) === name : name.test(b.textContent ?? ""),
  );
const click = (element: HTMLElement | undefined) => act(() => element!.click());

describe("What you can ask", () => {
  it("shows three lines, and a disclosure reveals the other two", () => {
    expect(lines()).toEqual(CAPABILITIES.slice(0, 3).map((capability) => capability.description));
    const more = button("Show 2 more")!;
    expect(more.getAttribute("aria-expanded")).toBe("false");
    const list = container.querySelector('[aria-labelledby="ask-label"] ul')!;
    expect(more.getAttribute("aria-controls")).toBe(list.id);

    click(more);
    expect(lines()).toEqual(CAPABILITIES.map((capability) => capability.description));
    expect(more.getAttribute("aria-expanded")).toBe("true");
    expect(more.textContent).toBe("Show fewer");
  });

  it("reaches every example of a line", () => {
    click(button("Show 2 more"));
    for (const capability of CAPABILITIES) {
      for (const example of capability.examples) {
        expect(button(example), example).toBeDefined();
      }
    }
    // The lookup line's fourth example waits behind its "+1" chip on a phone.
    const nvidia = button("How is Nvidia doing?")!;
    expect(nvidia.classList.contains("max-sm:hidden")).toBe(true);
    const chips = [...container.querySelectorAll("button")].filter((b) => b.textContent === "+1");
    expect(chips).toHaveLength(2);
    expect(chips[0].getAttribute("aria-label")).toBe("Show 1 more example");
    expect(chips[0].getAttribute("aria-expanded")).toBe("false");

    click(chips[0]);
    expect(nvidia.classList.contains("max-sm:hidden")).toBe(false);
    expect(chips[0].getAttribute("aria-expanded")).toBe("true");

    click(nvidia);
    expect(onDraft).toHaveBeenCalledWith("How is Nvidia doing?");
  });
});
