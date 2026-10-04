// @vitest-environment jsdom

import { createElement, memo } from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Presentation, Turn } from "../lib/types";

const { renderAnswer } = vi.hoisted(() => ({ renderAnswer: vi.fn() }));

vi.mock("./answer", () => ({
  Answer: memo(function MockAnswer(props: unknown) {
    renderAnswer(props);
    return createElement("div");
  }),
}));

import { Thread } from "./thread";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const PRESENTATION: Presentation = {
  intent: "lookup",
  intent_label: "Quarterly fact",
  banners: [],
  traces: [],
  citations: [],
  fact_card: null,
  table: null,
  chart: null,
  evidence: [],
  disclosures: [],
  essay: null,
  message: null,
  candidates: [],
  clarify_prompt: null,
  suggestions: [],
  message_tone: "info",
  headline: null,
  trends: [],
};

const TURNS: Turn[] = [
  {
    index: 0,
    message: "First question",
    presentation: PRESENTATION,
    candidate_slugs: [],
    clarify_enabled: false,
  },
  {
    index: 1,
    message: "Follow-up",
    presentation: PRESENTATION,
    candidate_slugs: [],
    clarify_enabled: false,
  },
];

describe("Thread answer rendering", () => {
  beforeEach(() => renderAnswer.mockClear());

  it("does not render finished answers again for a progress event", async () => {
    const onAsk = vi.fn();
    const props = {
      turns: TURNS,
      turn: {
        status: "running",
        message: "Another follow-up",
        progress: { done: 0, total: 2 },
        waking: false,
      } as const,
      onRetry: vi.fn(),
      onAsk,
      onStartOver: vi.fn(),
    };
    const container = document.createElement("div");
    const root = createRoot(container);

    act(() => {
      root.render(createElement(Thread, props));
    });
    expect(renderAnswer).toHaveBeenCalledTimes(2);

    act(() => {
      root.render(
        createElement(Thread, {
          ...props,
          onAsk: vi.fn(),
          turn: { ...props.turn, progress: { done: 1, total: 2 } },
        }),
      );
    });

    expect(renderAnswer).toHaveBeenCalledTimes(2);
    act(() => root.unmount());
  });
});
