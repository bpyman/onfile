"use client";

import { ArrowRight, ArrowUpRight, ChevronDown, ChevronsUpDown, Info, Route, ScanSearch, X } from "lucide-react";
import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
import { createPortal } from "react-dom";
import type { ClarifyChoice } from "@/lib/clarify";
import { inspectorOrder } from "@/lib/inspect";
import { answerFilings, splitNotes, type FilingLink } from "@/lib/notes";
import { pivotTable, type ShownTable } from "@/lib/pivot";
import { sortDescription, sortedRowIndices, sortedRowKeys, type TableSort } from "@/lib/table-sort";
import { cn, hardBreaks, parseLink, safeHref } from "@/lib/format";
import type {
  DisplayTrace,
  EvidenceItem,
  Pair,
  Presentation,
  QuarterlyFactCard,
  RuntimeKind,
} from "@/lib/types";
import { AnswerActions, hasTakeaway } from "./answer-actions";
import { AnswerChart } from "./answer-chart";
import { useRegionName } from "./answer-scope";
import { Clarify } from "./clarify";
import { CopyButton } from "./copy-button";
import { DataTable } from "./data-table";
import { FilingChanges } from "./filing-changes";
import { InspectContext } from "./inspect-context";
import { SafeMarkdown } from "./markdown";
import { Badge, Callout, ExternalLink, FilingButton, SectionLabel, type Tone } from "./ui";
import { WrittenAnswer } from "./written-answer";
import { isPhone, usePhone } from "@/lib/browser";

/** A clarification's buttons, as the thread wires them. */
export interface ClarifyControls {
  choices: ClarifyChoice[];
  live: boolean;
  onChoose: (slug: string) => void;
}

// A refusal warns; a question back to the analyst is neutral; an answer is primary.
const LABEL_TONE: Record<string, Tone> = {
  "Not answered": "warning",
  "Question for you": "neutral",
  Guide: "neutral",
};

/**
 * One answer. Every amount and label here is a string from the server's
 * presentation mapping (ADR 0006); nothing is formatted in the browser.
 * The headline, chart and table share one card; the sources sit under it,
 * behind one disclosure.
 */
export function Answer({
  question = "",
  conversation,
  presentation,
  clarify,
  onSuggest,
  runtime = null,
  demo = false,
}: {
  /** The question as the thread shows it, heading a copied answer. */
  question?: string;
  /** Every message sent up to this answer, for a shared link; the question alone by default. */
  conversation?: string[];
  presentation: Presentation;
  clarify?: ClarifyControls;
  /** Set on the latest answer only: sends a suggested question. */
  onSuggest?: (question: string) => void;
  /** The thread's runtime, for a shared link. */
  runtime?: RuntimeKind | null;
  /** A recorded answer shown while the service wakes. */
  demo?: boolean;
}) {
  const { fact_card, chart, table, message, evidence, traces, banners } = presentation;
  const { essay, citations, disclosures } = presentation;
  const trends = presentation.trends;
  // Several companies over several quarters read across: quarters down, companies along.
  const shown: ShownTable | null = useMemo(() => (table ? (pivotTable(table) ?? table) : null), [table]);
  const pivoted = Boolean(table && shown !== table);
  // Sorting the table re-orders the comparison chart's bars to match.
  const [sort, setSort] = useState<TableSort | null>(null);
  // Memoised on the table and the sort: a new array each render would also undo
  // the inspector's own memo below.
  const rowOrder = useMemo(() => (shown && sort ? sortedRowIndices(shown, sort) : null), [shown, sort]);
  const order = useMemo(() => (shown && !pivoted ? sortedRowKeys(shown, sort) : null), [shown, pivoted, sort]);
  const sortNote = useMemo(() => (shown && sort ? sortDescription(shown, sort) : null), [shown, sort]);
  const { footnotes, snapshot, notes } = splitNotes(banners);
  const filings = useMemo(() => answerFilings(presentation), [presentation]);

  const sources = useSources(evidence.length);
  const options = useMemo(() => inspectorOrder(evidence.length, shown, rowOrder), [evidence.length, shown, rowOrder]);
  const trendsName = useRegionName("Recent quarters");
  const figures = Boolean(chart || (shown && shown.rows.length > 0) || trends.length > 0);
  const label = demo ? "Demo data" : presentation.intent_label || presentation.intent;

  return (
    <InspectContext.Provider value={evidence.length > 0 ? sources.inspect : null}>
      <div className="min-w-0 space-y-4">
        <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
          <span className="flex min-w-0 items-center gap-1.5">
            <Badge tone={demo ? "warning" : (LABEL_TONE[label] ?? "primary")}>{label}</Badge>
            {demo && <span className="text-[11.5px] text-subtle">Recorded answer while the service wakes</span>}
          </span>
          {hasTakeaway(presentation) && !demo && (
            <AnswerActions
              question={question}
              conversation={conversation ?? [question]}
              presentation={presentation}
              table={shown}
              rowOrder={rowOrder}
              runtime={runtime}
            />
          )}
        </div>
        {figures ? (
          <article className="overflow-hidden rounded-2xl border border-border bg-surface shadow-[0_18px_40px_-32px_rgb(0_0_0/0.45)]">
            {(presentation.headline || notes.length > 0) && (
              <div className="px-4 py-4 sm:px-5">
                <Headline text={presentation.headline} />
                <CompactNotes notes={notes} spaced={Boolean(presentation.headline)} />
              </div>
            )}
            {trends.length > 0 && (
              <section aria-label={trendsName} className="grid border-t border-border first:border-t-0 sm:grid-cols-2 sm:divide-x sm:divide-border">
                {trends.map((trend, index) => (
                  <div key={trend.metric} className={cn(index > 0 && "border-t border-border sm:border-t-0")}>
                    <AnswerChart chart={trend} compact bare />
                  </div>
                ))}
              </section>
            )}
            {chart && (
              <div className="border-t border-border first:border-t-0">
                <AnswerChart chart={chart} order={order} sortNote={sortNote} captionNote={snapshot} bare />
              </div>
            )}
            {shown && shown.rows.length > 0 && (
              <div className="border-t border-border first:border-t-0">
                <DataTable table={shown} sort={sort} onSort={setSort} bare pivoted={pivoted} />
              </div>
            )}
            {(footnotes.length > 0 || (snapshot && !chart)) && (
              <footer className="space-y-1 border-t border-border bg-surface-2/40 px-4 py-2.5 text-xs leading-relaxed text-muted sm:px-5">
                {footnotes.map((note) => (
                  <p key={note}>{note}</p>
                ))}
                {snapshot && !chart && <SnapshotNote text={snapshot} />}
              </footer>
            )}
          </article>
        ) : (
          <>
            <Headline text={presentation.headline} />
            {fact_card ? <CompactNotes notes={[...notes, ...(snapshot ? [snapshot] : [])]} /> : <Notes banners={banners} />}
          </>
        )}
        {fact_card && <FactCard card={fact_card} footnotes={footnotes} />}
        {message &&
          (presentation.message_tone === "info" ? (
            <p className="break-words text-[15px] leading-relaxed text-fg">{message}</p>
          ) : (
            <Callout kind="warning">{message}</Callout>
          ))}
        {essay && (
          <WrittenAnswer
            essay={essay}
            citations={citations}
            title={disclosures.length > 0 ? "Summary of changes" : citations.length > 0 ? "Brief" : "Analysis"}
          />
        )}
        {disclosures.length > 0 && <FilingChanges items={disclosures} />}
        {clarify && clarify.choices.length > 0 && (
          <Clarify
            prompt={presentation.clarify_prompt}
            choices={clarify.choices}
            live={clarify.live}
            onChoose={clarify.onChoose}
          />
        )}
        {(evidence.length > 0 || traces.length > 0) && (
          <Sources
            open={sources.open}
            onToggle={sources.setOpen}
            filings={filings}
            evidenceCount={evidence.length}
          >
            {evidence.length > 0 && (
              <EvidenceInspector
                items={evidence}
                order={options}
                chosen={sources.chosen}
                onChoose={sources.setChosen}
                lit={sources.lit}
                sectionRef={sources.inspector}
              />
            )}
            {filings.length > 0 && <FilingList filings={filings} />}
            {traces.length > 0 && <Traces traces={traces} />}
          </Sources>
        )}
        {sources.sheet !== null && evidence[sources.sheet] && (
          <SourceSheet item={evidence[sources.sheet]} onClose={sources.closeSheet} />
        )}
        {onSuggest && (presentation.suggestions?.length ?? 0) > 0 && (
          <Suggestions items={presentation.suggestions} onSuggest={onSuggest} />
        )}
      </div>
    </InspectContext.Provider>
  );
}

/**
 * The Sources disclosure and what a clicked figure does with it: open it and
 * select the figure's source (a bottom sheet on a phone instead).
 */
function useSources(count: number) {
  const phone = usePhone();
  // Open on a wide screen; a phone keeps the answer short until asked.
  const [choice, setOpen] = useState<boolean | null>(null);
  const open = choice ?? !phone;
  const [chosen, setChosen] = useState(0);
  const [flash, setFlash] = useState(0);
  const [lit, setLit] = useState(false);
  const [sheet, setSheet] = useState<number | null>(null);
  const inspector = useRef<HTMLElement | null>(null);
  const pendingScroll = useRef(false);
  const dim = useRef<number | undefined>(undefined);

  // Once the opened inspector is drawn, bring it into view.
  useEffect(() => {
    if (!pendingScroll.current || !open) return;
    pendingScroll.current = false;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    inspector.current?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "center" });
  }, [open, flash]);

  useEffect(() => () => window.clearTimeout(dim.current), []);

  const inspect = useCallback(
    (index: number) => {
      if (index < 0 || index >= count) return;
      setChosen(index);
      if (isPhone()) {
        setSheet(index);
        return;
      }
      pendingScroll.current = true;
      setOpen(true);
      setFlash((value) => value + 1);
      // A brief ring on the inspector says which panel the click filled.
      setLit(true);
      window.clearTimeout(dim.current);
      dim.current = window.setTimeout(() => setLit(false), 1400);
    },
    [count],
  );

  return { open, setOpen, chosen, setChosen, lit, sheet, closeSheet: () => setSheet(null), inspect, inspector };
}

function Headline({ text }: { text?: string | null }) {
  if (!text) return null;
  return (
    <p className="max-w-[60ch] text-pretty break-words text-[17px] font-medium leading-snug tracking-[-0.012em] text-fg sm:text-[19px]">
      {text}
    </p>
  );
}

/** Period and ordering notes: one quiet line under the headline, not a box above the answer. */
function CompactNotes({ notes, spaced = true }: { notes: string[]; spaced?: boolean }) {
  if (notes.length === 0) return null;
  return (
    <p className={cn("flex max-w-[75ch] items-start gap-1.5 text-[12.5px] leading-relaxed text-muted", spaced && "mt-2")}>
      <Info className="mt-[3px] size-3.5 shrink-0 text-subtle" aria-hidden />
      <span className="min-w-0 break-words">{notes.join(" ")}</span>
    </p>
  );
}

const SNAPSHOT_HELP =
  "The universe snapshot is a dated list of US-listed operating companies with their market caps. Rankings read it; it is not rescreened live.";

export function SnapshotNote({ text }: { text: string }) {
  return (
    <p className="cursor-help" title={SNAPSHOT_HELP}>
      {text}
    </p>
  );
}

/** An essay's or a refusal's notes: one soft callout, a line each. */
function Notes({ banners }: { banners: string[] }) {
  if (banners.length === 0) return null;
  if (banners.length === 1) return <Callout kind="info">{banners[0]}</Callout>;
  return (
    <Callout kind="info">
      <ul className="divide-y divide-primary/15">
        {banners.map((banner) => (
          <li key={banner} className="py-1.5 first:pt-0 last:pb-0">
            {banner}
          </li>
        ))}
      </ul>
    </Callout>
  );
}

function Suggestions({
  items,
  onSuggest,
}: {
  items: string[];
  onSuggest: (question: string) => void;
}) {
  return (
    <nav aria-label="Suggested next questions" className="flex flex-wrap items-center gap-2 pt-1">
      <span className="text-[11px] font-medium uppercase tracking-[0.08em] text-subtle">Next</span>
      {items.map((item) => (
        <button
          key={item}
          type="button"
          onClick={() => onSuggest(item)}
          className="group inline-flex min-h-9 min-w-0 max-w-full items-center gap-1.5 rounded-full border border-border-strong bg-surface-2/60 px-3.5 py-1.5 text-left text-[13px] text-fg transition-[background,border,color] hover:border-primary/60 hover:bg-primary-soft hover:text-primary"
        >
          <span className="min-w-0 break-words [overflow-wrap:anywhere]">{item}</span>
          <ArrowRight className="size-3.5 text-subtle transition-transform group-hover:translate-x-0.5 group-hover:text-primary" aria-hidden />
        </button>
      ))}
    </nav>
  );
}

const CHANGE_TONE = {
  up: "border-positive/25 bg-positive-soft text-positive",
  down: "border-negative/25 bg-negative-soft text-negative",
  flat: "border-border bg-surface-2 text-muted",
} as const;

const CONCEPT_HELP = "The XBRL tag the company filed this amount under (its “concept”).";

export function FactCard({ card, footnotes = [] }: { card: QuarterlyFactCard; footnotes?: string[] }) {
  // A derived quarter's form is the filings it came from (a 10-K less a 10-Q),
  // not the quarter's own report; the kind badge says so and keeps the forms in its title.
  const derived = card.period_label.startsWith("Derived");
  const kind = card.kind_label || (derived ? "Derived quarter" : "Quarterly fact");
  const name = useRegionName(`${card.metric_header}, ${card.company_name}`);
  return (
    <section
      aria-label={name}
      className="relative overflow-hidden rounded-2xl border border-border bg-surface shadow-[0_18px_40px_-32px_rgb(0_0_0/0.45)]"
    >
      <span
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/70 to-transparent"
      />
      {/* The glow reads as depth on a dark surface and as a smudge on a light one. */}
      <span
        aria-hidden
        className="pointer-events-none absolute -right-16 -top-28 hidden h-56 w-80 rounded-full bg-primary/10 blur-3xl dark:block"
      />
      <div className="relative p-5 sm:p-6">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <span className="num flex h-9 min-w-9 shrink-0 items-center justify-center rounded-lg border border-border-strong bg-surface-2 px-2 text-[11px] font-semibold text-fg">
              {card.ticker}
            </span>
            <div className="min-w-0 truncate text-sm font-medium text-fg">{card.company_name}</div>
          </div>
          <div className="flex shrink-0 flex-wrap items-center justify-end gap-1.5">
            <span title={derived && card.form ? `From ${card.form} filings` : undefined}>
              <Badge tone={kind === "Quarterly fact" ? "neutral" : "primary"}>{kind}</Badge>
            </span>
            {card.form && !derived && <Badge className="num">{card.form}</Badge>}
          </div>
        </div>
        <div className="mt-6">
          <SectionLabel>{card.metric_header}</SectionLabel>
          <div className="figure mt-2 text-[40px] font-semibold leading-none text-fg [overflow-wrap:anywhere] sm:text-[52px]">
            {card.amount}
          </div>
          {card.changes.length > 0 && (
            <ul aria-label="Change" className="mt-3.5 flex flex-wrap gap-1.5">
              {card.changes.map((change) => (
                <li
                  key={change.label}
                  title={change.title}
                  className={cn(
                    "num inline-flex h-6 items-center rounded-md border px-2 text-[12px] font-medium",
                    CHANGE_TONE[change.direction],
                  )}
                >
                  {change.label}
                </li>
              ))}
            </ul>
          )}
          <div className="mt-3 text-[13px] text-muted">{card.period_label}</div>
          {footnotes.map((note) => (
            <p key={note} className="mt-2 max-w-prose text-[12px] leading-relaxed text-subtle">
              {note}
            </p>
          ))}
        </div>
      </div>
      <div className="relative grid border-t border-border bg-surface-2/50 sm:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_auto]">
        {card.accession_number && (
          <FactField label="Accession number">
            <span className="num truncate">{card.accession_number}</span>
            <CopyButton value={card.accession_number} label="accession number" />
          </FactField>
        )}
        {card.concept && (
          <FactField label="Concept" help={CONCEPT_HELP}>
            <span className="num truncate" title={card.concept}>
              {card.concept_short || card.concept}
            </span>
          </FactField>
        )}
        {safeHref(card.source_url) && (
          <div className="flex items-center border-t border-border px-5 py-3 sm:border-l sm:border-t-0 sm:px-4">
            <FilingButton href={card.source_url} emphasis />
          </div>
        )}
      </div>
    </section>
  );
}

function FactField({ label, help, children }: { label: string; help?: string; children: ReactNode }) {
  return (
    <div className="min-w-0 border-border px-5 py-3 [&+&]:border-t sm:[&+&]:border-l sm:[&+&]:border-t-0 sm:px-4 sm:first:pl-6">
      <div className={cn("text-[10.5px] font-medium uppercase tracking-[0.08em] text-subtle", help && "cursor-help")} title={help}>
        {label}
      </div>
      <div className="mt-1 flex min-w-0 items-center gap-1 text-[13px] text-fg">{children}</div>
    </div>
  );
}

/** "Sources · 3 filings": the inspector, the filings read, and how the answer was fetched. */
function Sources({
  open,
  onToggle,
  filings,
  evidenceCount,
  children,
}: {
  open: boolean;
  onToggle: (open: boolean) => void;
  filings: FilingLink[];
  evidenceCount: number;
  children: ReactNode;
}) {
  const count = filings.length;
  const detail = count > 0 ? `${count} ${count === 1 ? "filing" : "filings"}` : `${evidenceCount} ${evidenceCount === 1 ? "figure" : "figures"}`;
  return (
    <details
      open={open}
      onToggle={(event) => onToggle(event.currentTarget.open)}
      className="group/sources rounded-xl border border-border bg-surface/60"
    >
      <summary className="flex cursor-pointer list-none items-center gap-2 rounded-xl px-4 py-3 text-[13px] font-medium text-fg transition-colors hover:bg-surface-2/60 [&::-webkit-details-marker]:hidden">
        <ScanSearch className="size-4 text-primary" aria-hidden />
        Sources
        <span className="font-normal text-subtle">· {detail}</span>
        <span className="ml-auto hidden text-[11.5px] font-normal text-subtle sm:inline">Click any figure to see its source</span>
        <ChevronDown className="size-4 shrink-0 text-subtle transition-transform group-open/sources:rotate-180" aria-hidden />
      </summary>
      <div className="space-y-4 border-t border-border p-3 sm:p-4">{children}</div>
    </details>
  );
}

function FilingList({ filings }: { filings: FilingLink[] }) {
  return (
    <section aria-label={useRegionName("Filings read")}>
      <SectionLabel className="mb-2">Filings read</SectionLabel>
      <ul className="flex flex-wrap gap-1.5">
        {filings.map((filing) => (
          <li key={filing.url}>
            <a
              href={filing.url}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex max-w-full items-center gap-1 rounded-md border border-border bg-surface px-2 py-1 text-[12px] text-fg transition-colors hover:border-primary/50 hover:text-primary"
            >
              <span className="min-w-0 truncate">{filing.label}</span>
              <ArrowUpRight className="size-3 shrink-0" aria-hidden />
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}

const SELECTION_HELP = "How the figure was chosen from the filing: which period, form and rule picked it.";

export function EvidenceInspector({
  items,
  order,
  chosen,
  onChoose,
  lit = false,
  sectionRef,
}: {
  items: EvidenceItem[];
  /** Option order: the table's, then the rest. */
  order?: number[];
  chosen: number;
  onChoose: (index: number) => void;
  /** A figure was just clicked: highlight the source it opened. */
  lit?: boolean;
  sectionRef?: RefObject<HTMLElement | null>;
}) {
  const selectId = useId();
  const index = Math.min(Math.max(chosen, 0), items.length - 1);
  const item = items[index];
  const options = order && order.length === items.length ? order : items.map((_, each) => each);
  const position = options.indexOf(index);
  const name = useRegionName("Evidence inspector");
  return (
    <section
      ref={sectionRef}
      aria-label={name}
      className={cn(
        "scroll-mt-24 overflow-hidden rounded-xl border border-border bg-surface transition-[box-shadow,border-color] duration-500",
        lit && "border-primary/60 shadow-[0_0_0_4px_var(--primary-soft)]",
      )}
    >
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-2.5">
        <div className="flex items-center gap-2 text-[13px] font-medium text-fg">Inspect exact source</div>
        <span className="num text-[11px] text-subtle">
          {items.length === 1 ? "1 source" : `${position + 1} of ${items.length} sources`}
        </span>
      </header>
      {items.length > 1 && (
        <div className="relative border-b border-border px-4 py-2.5">
          <label htmlFor={selectId} className="sr-only">
            Evidence item
          </label>
          <select
            id={selectId}
            value={index}
            onChange={(event) => onChoose(Number(event.target.value))}
            className="h-8 w-full appearance-none truncate rounded-lg border border-border bg-surface-2 pl-2.5 pr-8 text-[13px] text-fg outline-none hover:border-border-strong focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary"
          >
            {options.map((option, at) => (
              <option key={`${items[option].label}-${option}`} value={option}>
                {at + 1}. {items[option].label}
              </option>
            ))}
          </select>
          <ChevronsUpDown
            className="pointer-events-none absolute right-6 top-1/2 size-3.5 -translate-y-1/2 text-subtle"
            aria-hidden
          />
        </div>
      )}
      <span className="sr-only" aria-live="polite">
        {lit ? `Showing the source of ${item.label}` : ""}
      </span>
      <EvidenceFields item={item} />
      {safeHref(item.source_url) && (
        <footer className="flex justify-end border-t border-border bg-surface-2/40 px-4 py-2.5">
          <FilingButton href={item.source_url} />
        </footer>
      )}
    </section>
  );
}

function EvidenceFields({ item }: { item: EvidenceItem }) {
  const company = [item.company_name, item.ticker].filter(Boolean).join(" · ");
  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-3.5 px-4 py-4">
      <EvidenceField pair label="Amount">
        <span className="figure text-xl font-semibold text-fg">{item.amount}</span>
      </EvidenceField>
      <EvidenceField pair label="Exact amount" hidden={!item.raw_amount}>
        <code
          className="num rounded-md border border-border bg-surface-2 px-1.5 py-0.5 text-[12.5px] text-fg"
          title={item.raw_amount}
        >
          {item.exact_amount || item.raw_amount}
        </code>
        <CopyButton value={item.raw_amount} label="exact amount" />
      </EvidenceField>
      <EvidenceField label="Company" hidden={!company}>
        {company}
      </EvidenceField>
      <EvidenceField label="Period" hidden={!item.period_label}>
        {item.period_label}
      </EvidenceField>
      <EvidenceField pair label="CIK" hidden={!item.cik} help="The SEC's Central Index Key: the company's filer number.">
        <span className="num">{item.cik}</span>
        <CopyButton value={item.cik} label="CIK" />
      </EvidenceField>
      <EvidenceField pair label="Form" hidden={!item.form}>
        <span className="num">{item.form}</span>
      </EvidenceField>
      <EvidenceField label="Accession number" hidden={!item.accession_number}>
        <span className="num">{item.accession_number}</span>
        <CopyButton value={item.accession_number} label="accession number" />
      </EvidenceField>
      <EvidenceField label="Concept" hidden={!item.concept} help={CONCEPT_HELP}>
        <span className="num break-all">{item.concept}</span>
      </EvidenceField>
      <EvidenceField label="How it was chosen" hidden={!item.selection_rule} wide help={SELECTION_HELP}>
        <span className="min-w-0 text-muted [overflow-wrap:anywhere]">{item.selection_rule}</span>
      </EvidenceField>
    </dl>
  );
}

/** A phone's inspector: the clicked figure's source in a sheet over the answer. */
function SourceSheet({ item, onClose }: { item: EvidenceItem; onClose: () => void }) {
  const close = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    close.current?.focus();
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", escape);
    return () => {
      window.removeEventListener("keydown", escape);
      previous?.focus({ preventScroll: true });
    };
  }, [onClose]);
  // On the body, above the pinned question box: an answer's fade-in would otherwise confine its layer.
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end sm:hidden">
      <button type="button" aria-hidden tabIndex={-1} onClick={onClose} className="absolute inset-0 bg-black/40 backdrop-blur-[1px]" />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="relative max-h-[78dvh] w-full animate-fade-up overflow-y-auto rounded-t-2xl border-t border-border-strong bg-surface pb-[env(safe-area-inset-bottom)] shadow-2xl"
      >
        <div className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-border bg-surface px-4 py-3">
          <div id={titleId} className="min-w-0 text-[13px] font-medium text-fg">
            <span className="block text-[10.5px] font-medium uppercase tracking-[0.08em] text-subtle">Source</span>
            <span className="block truncate">{item.label}</span>
          </div>
          <button
            ref={close}
            type="button"
            onClick={onClose}
            aria-label="Close source"
            className="inline-flex size-8 shrink-0 items-center justify-center rounded-lg text-muted hover:bg-surface-2 hover:text-fg"
          >
            <X className="size-4" aria-hidden />
          </button>
        </div>
        <EvidenceFields item={item} />
        {safeHref(item.source_url) && (
          <div className="flex justify-end border-t border-border px-4 py-3">
            <FilingButton href={item.source_url} emphasis />
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}

function EvidenceField({
  label,
  hidden = false,
  wide = false,
  pair = false,
  help,
  children,
}: {
  label: string;
  hidden?: boolean;
  /** Spans both columns at every width. */
  wide?: boolean;
  /** Short enough to sit beside its neighbour even on a phone. */
  pair?: boolean;
  /** A plain-English gloss for a filing term, shown on hover. */
  help?: string;
  children: ReactNode;
}) {
  if (hidden) return null;
  return (
    <div className={cn("min-w-0", wide ? "col-span-2" : pair ? "col-span-1" : "col-span-2 sm:col-span-1")}>
      <dt className={cn("text-[10.5px] font-medium uppercase tracking-[0.08em] text-subtle", help && "cursor-help")} title={help}>
        {label}
      </dt>
      <dd className="mt-1 flex min-w-0 items-center gap-1 text-[13px] text-fg">{children}</dd>
    </div>
  );
}

const TRACES_SHOWN = 5;

export function Traces({ traces }: { traces: DisplayTrace[] }) {
  // A window over several quarters makes a step per cell; show the first few.
  const [all, setAll] = useState(false);
  const shown = all ? traces : traces.slice(0, TRACES_SHOWN);
  const name = useRegionName("How this answer was fetched");
  return (
    <section aria-label={name}>
      <SectionLabel className="mb-2">How this answer was fetched</SectionLabel>
      <div className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">
        {shown.map((trace, index) => (
          <details key={`${trace.header}-${index}`} className="group">
            <summary className="flex cursor-pointer list-none items-center gap-3 px-4 py-3 text-[13px] transition-colors hover:bg-surface-2/60 [&::-webkit-details-marker]:hidden">
              <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-primary-soft text-primary">
                <Route className="size-3.5" aria-hidden />
              </span>
              <span className="min-w-0 flex-1 text-fg">{trace.header}</span>
              <ChevronDown
                className="size-4 shrink-0 text-subtle transition-transform group-open:rotate-180"
                aria-hidden
              />
            </summary>
            <div className="grid gap-5 border-t border-border bg-surface-2/35 px-4 py-4 md:grid-cols-2">
              {trace.inputs.length > 0 && <TraceGroup title="Request" fields={trace.inputs} />}
              {trace.outputs.length > 0 && <TraceGroup title="Result" fields={trace.outputs} />}
            </div>
          </details>
        ))}
        {traces.length > shown.length && (
          <button
            type="button"
            onClick={() => setAll(true)}
            className="flex w-full items-center justify-center gap-1.5 px-4 py-2.5 text-[13px] text-muted transition-colors hover:bg-surface-2/60 hover:text-fg"
          >
            Show all {traces.length} steps
            <ChevronDown className="size-4" aria-hidden />
          </button>
        )}
      </div>
    </section>
  );
}

function TraceGroup({ title, fields }: { title: string; fields: Pair[] }) {
  return (
    <div className="min-w-0">
      <div className="mb-2 text-[10.5px] font-medium uppercase tracking-[0.08em] text-subtle">
        {title}
      </div>
      {/* Label over value on a phone: side by side, the value column is a few characters wide. */}
      <dl className="grid grid-cols-1 gap-x-4 gap-y-1.5 text-[12.5px] sm:grid-cols-[minmax(6.5rem,auto)_minmax(0,1fr)]">
        {fields.map(([label, value], index) => (
          <TraceRow key={`${label}-${index}`} label={label} value={value} />
        ))}
      </dl>
    </div>
  );
}

function TraceRow({ label, value }: { label: string; value: string }) {
  if (!value) {
    if (!label) return <div aria-hidden className="col-span-full h-2" />;
    return <dt className="col-span-full mt-1 font-medium text-fg">{label}</dt>;
  }
  if (value.includes("\n")) {
    return (
      <div className="col-span-full min-w-0">
        {label && <dt className="mb-1 font-medium text-fg">{label}</dt>}
        <dd>
          <SafeMarkdown text={hardBreaks(value)} className="text-[12.5px] text-muted" />
        </dd>
      </div>
    );
  }
  const link = parseLink(value);
  return (
    <>
      <dt className="mt-1 text-subtle first:mt-0 sm:mt-0">{label}</dt>
      <dd className="min-w-0 break-words text-fg">
        {link ? (
          <ExternalLink href={link.href} className="break-all">
            {link.text}
          </ExternalLink>
        ) : (
          value
        )}
      </dd>
    </>
  );
}
