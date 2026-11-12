// @vitest-environment jsdom

import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ClarifyChoice } from "../lib/clarify";
import { Clarify } from "./clarify";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// Captured from "Why did Target's gross margin jump last quarter?" on the live demo.
const COMPARISON: ClarifyChoice[] = [
  { slug: "year_over_year", label: "The same quarter a year earlier (year over year)", chosen: false },
  { slug: "sequential", label: "The quarter before (sequential)", chosen: false },
];

let root: ReturnType<typeof createRoot> | null = null;

function render(choices: ClarifyChoice[], onChoose = vi.fn()): HTMLElement {
  const container = document.createElement("div");
  root = createRoot(container);
  act(() => {
    root!.render(createElement(Clarify, { prompt: "Compared with what?", choices, live: true, onChoose }));
  });
  return container;
}

afterEach(() => {
  act(() => root?.unmount());
  root = null;
});

const buttons = (container: HTMLElement) => [...container.querySelectorAll("button")];

describe("Clarify", () => {
  it("shows a comparison-base question with no id under its labels", () => {
    const container = render(COMPARISON);
    expect(buttons(container).map((button) => button.textContent)).toEqual(COMPARISON.map((c) => c.label));
    expect(container.textContent).not.toContain("_");
    for (const element of container.querySelectorAll("*")) {
      for (const name of ["title", "aria-label"]) expect(element.getAttribute(name) ?? "").not.toContain("_");
    }
  });

  it("shows a metric's slug as words when the label reads differently", () => {
    const container = render([
      { slug: "eps_diluted", label: "Diluted EPS", chosen: false },
      { slug: "net_income", label: "Net income", chosen: false },
    ]);
    expect(buttons(container).map((button) => button.textContent)).toEqual(["Diluted EPSeps diluted", "Net income"]);
  });

  it("still sends the slug", () => {
    const onChoose = vi.fn();
    const container = render(COMPARISON, onChoose);
    act(() => buttons(container)[0].click());
    expect(onChoose).toHaveBeenCalledWith("year_over_year");
  });
});
