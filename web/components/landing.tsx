"use client";

import {
  ArrowUpRight,
  ChevronDown,
  FileDiff,
  Layers,
  LineChart,
  ListOrdered,
  Loader2,
  ReceiptText,
  ScanSearch,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useId, useState } from "react";
import { loadDemoAnswers } from "@/lib/demo-answers";
import { cn } from "@/lib/format";
import type { Meta, QuarterlyFactCard } from "@/lib/types";
import { Button, Callout, SectionLabel } from "./ui";

const STORY_ICONS: Record<string, LucideIcon> = {
  "Verify a quarterly fact": ReceiptText,
  "Compare four quarters": LineChart,
  "Rank then inspect filings": ListOrdered,
  "What changed in the 10-Q": FileDiff,
};

// What the landing page offers before /api/meta answers (a sleeping host takes
// about a minute): the API's guided stories (storefront.py) and the examples
// every runtime answers. Meta's own lists replace these when they arrive.
const DEFAULT_STORIES: Meta["guided_stories"] = [
  { label: "Verify a quarterly fact", question: "What was Microsoft's latest quarterly pretax income?" },
  { label: "Compare four quarters", question: "What was Microsoft's quarterly revenue over the last four quarters?" },
  { label: "Rank then inspect filings", question: "What are the top 10 tech companies and R&D spend for each?" },
  { label: "What changed in the 10-Q", question: "What changed in Microsoft's latest 10-Q?" },
];
const DEFAULT_CAPABILITIES: Meta["capabilities"] = [
  {
    description:
      "Look up any quarter's financials, EPS, cash flow, or market cap for any operating publicly-listed US company",
    examples: [
      "What was Microsoft's latest quarterly revenue?",
      "Apple diluted EPS in Q3 FY2025",
      "Microsoft free cash flow over the last four quarters",
      "How is Nvidia doing?",
    ],
  },
  {
    description: "Compare companies on metrics, rank by market cap, or combine rank and lookup",
    examples: [
      "Compare Eli Lilly and Merck net margins",
      "What are the top 10 tech companies and R&D spend for each?",
      "Top 5 semiconductor companies by revenue",
    ],
  },
  {
    description: "Stay on the same thread to extend the current analysis, or start a new one",
    examples: ["add Apple", "now add operating margin", "make that the last four quarters", "show year-over-year"],
  },
];

// "What you can ask" opens on three lines, with a button for the rest. A line
// shows every example; on a phone, where four wrap past two rows, three show
// and a "+N" chip opens the rest.
const CAPABILITIES_SHOWN = 3;
const EXAMPLES_SHOWN_ON_A_PHONE = 3;

/** First screen: guided stories, what you can ask, and the metric catalogue behind a disclosure. */
export function Landing({
  meta,
  waking,
  error,
  disabled,
  onAsk,
  onStory,
  onDraft,
  onRetry,
}: {
  meta: Meta | null;
  waking: boolean;
  error: string | null;
  disabled: boolean;
  onAsk: (question: string) => void;
  /** A guided story; asked like any question, with its recorded answer at hand while the API wakes. */
  onStory?: (question: string) => void;
  onDraft: (question: string) => void;
  onRetry: () => void;
}) {
  const stories = meta?.guided_stories.length ? meta.guided_stories : DEFAULT_STORIES;
  const allCapabilities = meta?.capabilities.length ? meta.capabilities : DEFAULT_CAPABILITIES;
  const [allShown, setAllShown] = useState(false);
  const hidden = allCapabilities.length - CAPABILITIES_SHOWN;
  const capabilities = allShown ? allCapabilities : allCapabilities.slice(0, CAPABILITIES_SHOWN);
  const listId = useId();
  return (
    <div className="animate-fade-up">
      <section className="grid gap-10 pb-7 pt-6 sm:pb-12 sm:pt-14 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)] lg:items-center">
        <div>
          <p className="hidden items-center gap-2 rounded-full border border-border bg-surface/70 px-2.5 py-1 text-[11px] font-medium text-muted sm:inline-flex">
            <span className="size-1.5 rounded-full bg-positive shadow-[0_0_0_3px] shadow-positive/15" />
            SEC 10-Q facts with provenance on every number
          </p>
          <h1 className="max-w-3xl text-balance text-[26px] font-semibold leading-[1.12] tracking-tight sm:mt-5 sm:text-[44px] sm:leading-[1.1]">
            Ask about a company.{" "}
            <span className="text-muted">Get the number and the filing behind it.</span>
          </h1>
          <p className="mt-3 max-w-2xl text-pretty text-[15px] leading-relaxed text-muted sm:mt-4">
            Every amount comes from an SEC filing, formatted by code rather than the model, with its source a click away.
          </p>
        </div>
        <HeroPreview />
      </section>

      {error && (
        <Callout kind="error" className="mb-8">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span>{error}</span>
            <Button size="sm" variant="outline" onClick={onRetry}>
              Try again
            </Button>
          </div>
        </Callout>
      )}

      <section aria-labelledby="stories-label">
        <div className="mb-3 flex items-center justify-between gap-3">
          <SectionLabel>
            <span id="stories-label">Guided stories</span>
          </SectionLabel>
          {waking && !meta && !error && <Waking />}
        </div>
        {/* A phone swipes through the stories in one row, so the first shows above the fold. */}
        <div className="-mx-4 flex snap-x snap-mandatory gap-3 overflow-x-auto px-4 pb-1 [scrollbar-width:none] sm:mx-0 sm:grid sm:grid-cols-2 sm:overflow-visible sm:px-0 sm:pb-0">
          {stories.map((story) => {
            const Icon = STORY_ICONS[story.label] ?? Layers;
            return (
              <button
                key={story.label}
                type="button"
                disabled={disabled}
                onClick={() => (onStory ?? onAsk)(story.question)}
                className="group relative flex w-[80%] shrink-0 snap-start flex-col justify-start gap-3 overflow-hidden rounded-xl border border-border bg-surface p-4 text-left transition-[border-color,background-color,box-shadow] hover:border-primary/40 hover:shadow-[0_0_0_4px] hover:shadow-primary/5 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
              >
                <span
                  aria-hidden
                  className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/50 to-transparent opacity-0 transition-opacity group-hover:opacity-100"
                />
                <span className="flex w-full items-center justify-between">
                  <span className="flex size-8 items-center justify-center rounded-lg border border-border bg-surface-2 text-primary">
                    <Icon className="size-4" aria-hidden />
                  </span>
                  <ArrowUpRight
                    className="size-4 text-subtle transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-primary"
                    aria-hidden
                  />
                </span>
                <span>
                  <span className="block break-words text-sm font-medium text-fg">{story.label}</span>
                  <span className="mt-1 block break-words text-[13px] leading-snug text-muted">
                    {story.question}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      </section>

      <div className="mt-12 grid gap-8 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <section aria-labelledby="ask-label">
          <SectionLabel className="mb-3">
            <span id="ask-label">What you can ask</span>
          </SectionLabel>
          <ul
            id={listId}
            className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface"
          >
            {capabilities.map((capability) => (
              <Capability key={capability.description} capability={capability} onDraft={onDraft} />
            ))}
          </ul>
          {hidden > 0 && (
            <button
              type="button"
              aria-expanded={allShown}
              aria-controls={listId}
              onClick={() => setAllShown((shown) => !shown)}
              className="mt-2 inline-flex min-h-9 items-center gap-1 rounded-md px-1 text-[13px] font-medium text-muted underline-offset-4 hover:text-fg hover:underline"
            >
              {allShown ? "Show fewer" : `Show ${hidden} more`}
              <ChevronDown className={cn("size-3.5 transition-transform", allShown && "rotate-180")} aria-hidden />
            </button>
          )}
        </section>
        {meta && meta.metric_groups.length > 0 && (
          <section aria-labelledby="metrics-label">
            <SectionLabel className="mb-3">
              <span id="metrics-label">Supported metrics</span>
            </SectionLabel>
            <details className="group overflow-hidden rounded-xl border border-border bg-surface">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3.5 text-[13px] text-fg transition-colors hover:bg-surface-2/60 [&::-webkit-details-marker]:hidden">
                <span>
                  See all metrics
                  <span className="ml-1.5 text-subtle">
                    · {meta.metric_groups.reduce((total, group) => total + group.names.length, 0)} reported, calculated and market figures
                  </span>
                </span>
                <ChevronDown className="size-4 shrink-0 text-subtle transition-transform group-open:rotate-180" aria-hidden />
              </summary>
              <div className="divide-y divide-border border-t border-border">
                {meta.metric_groups.map((group) => (
                  <div key={group.title} className="px-4 py-3.5">
                    <div className="mb-2 text-xs font-medium text-muted">{group.title}</div>
                    <ul className="flex flex-wrap gap-1.5">
                      {group.names.map((name) => (
                        <li
                          key={name}
                          className="rounded-md border border-border/80 px-1.5 py-0.5 text-[11.5px] text-fg/85"
                        >
                          {name}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </details>
          </section>
        )}
      </div>
    </div>
  );
}

/** One line of "What you can ask": its examples put a question in the box. */
function Capability({
  capability,
  onDraft,
}: {
  capability: Meta["capabilities"][number];
  onDraft: (question: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const rest = capability.examples.length - EXAMPLES_SHOWN_ON_A_PHONE;
  const groupId = useId();
  return (
    <li className="px-4 py-3.5">
      <p className="text-[13px] leading-snug text-fg">{capability.description}</p>
      <div id={groupId} className="mt-2.5 flex flex-wrap gap-1.5">
        {capability.examples.map((example, index) => (
          <button
            key={example}
            type="button"
            onClick={() => onDraft(example)}
            title="Put this in the question box"
            className={cn(
              "max-w-full break-words rounded-md border border-border bg-surface-2 px-2 py-1 text-left text-xs text-muted transition-colors [overflow-wrap:anywhere] hover:border-border-strong hover:text-fg",
              !open && index >= EXAMPLES_SHOWN_ON_A_PHONE && "max-sm:hidden",
            )}
          >
            {example}
          </button>
        ))}
        {rest > 0 && (
          <button
            type="button"
            aria-expanded={open}
            aria-controls={groupId}
            aria-label={open ? "Show fewer examples" : `Show ${rest} more example${rest === 1 ? "" : "s"}`}
            onClick={() => setOpen((shown) => !shown)}
            className="num rounded-md border border-dashed border-border-strong px-2 py-1 text-xs font-medium text-muted transition-colors hover:border-primary/50 hover:text-fg sm:hidden"
          >
            {open ? "Fewer" : `+${rest}`}
          </button>
        )}
      </div>
    </li>
  );
}

/**
 * A wide screen's first view shows what an answer looks like: the first guided
 * story's recorded fact card (demo-answers.json), drawn small. Loaded only there.
 */
function HeroPreview() {
  const [card, setCard] = useState<QuarterlyFactCard | null>(null);
  useEffect(() => {
    if (!window.matchMedia("(min-width: 1024px)").matches) return;
    let live = true;
    void loadDemoAnswers()
      .then((answers) => {
        const first = [...answers.values()].find((answer) => answer.fact_card)?.fact_card ?? null;
        if (live) setCard(first);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);
  return (
    <div aria-hidden className="relative hidden lg:block">
      <div className="pointer-events-none absolute -inset-6 rounded-[2rem] bg-[radial-gradient(closest-side,var(--glow),transparent)]" />
      <div
        className={cn(
          "relative rotate-[0.6deg] overflow-hidden rounded-2xl border border-border bg-surface shadow-[0_30px_60px_-36px_rgb(0_0_0/0.55)] transition-opacity duration-500",
          card ? "opacity-100" : "opacity-0",
        )}
      >
        {card && (
          <>
            <div className="flex items-center justify-between gap-3 px-5 pt-5">
              <span className="flex min-w-0 items-center gap-2.5">
                <span className="num flex h-8 min-w-8 items-center justify-center rounded-lg border border-border-strong bg-surface-2 px-1.5 text-[10.5px] font-semibold text-fg">
                  {card.ticker}
                </span>
                <span className="truncate text-[13px] font-medium text-fg">{card.company_name}</span>
              </span>
              <span className="rounded-md border border-primary/25 bg-primary-soft px-1.5 py-0.5 text-[10.5px] font-medium text-primary">
                {card.kind_label || "Quarterly fact"}
              </span>
            </div>
            <div className="px-5 pb-5 pt-5">
              <SectionLabel>{card.metric_header}</SectionLabel>
              <div className="figure mt-1.5 text-[40px] font-semibold leading-none text-fg">{card.amount}</div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {card.changes.map((change) => (
                  <span
                    key={change.label}
                    className={cn(
                      "num rounded-md border px-1.5 py-0.5 text-[11px] font-medium",
                      change.direction === "down"
                        ? "border-negative/25 bg-negative-soft text-negative"
                        : "border-positive/25 bg-positive-soft text-positive",
                    )}
                  >
                    {change.label}
                  </span>
                ))}
              </div>
              <div className="mt-3 text-[12px] text-muted">{card.period_label}</div>
            </div>
            <div className="flex items-center justify-between gap-3 border-t border-border bg-surface-2/50 px-5 py-3 text-[11.5px] text-muted">
              <span className="num truncate">
                {card.form} {card.accession_number}
              </span>
              <span className="inline-flex shrink-0 items-center gap-1 text-primary">
                <ScanSearch className="size-3.5" />
                Source
              </span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

/** "Waking the analysis service… 12 s", counted from the visit: a sleeping host takes about a minute. */
function Waking() {
  const [seconds, setSeconds] = useState<number | null>(null);
  useEffect(() => {
    const tick = () => setSeconds(Math.floor(performance.now() / 1000));
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, []);
  return (
    <span className="flex items-center gap-1.5 text-xs text-muted">
      <Loader2 className="size-3.5 animate-spin text-primary" aria-hidden />
      <span role="status">Waking the analysis service…</span>
      {seconds !== null && (
        <span className="num text-subtle" aria-hidden>
          {seconds} s
        </span>
      )}
    </span>
  );
}
