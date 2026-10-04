"use client";

import { CalendarClock, Plus, X } from "lucide-react";
import { useId, useRef, type ToggleEvent } from "react";
import { cn, splitBanner } from "@/lib/format";
import { turnCounterLabel } from "@/lib/turn-state";
import type { ChipEdit, QuickAction, QuickActions, RuntimeGuide as Guide, RuntimeKind } from "@/lib/types";
import { RuntimeGuide } from "./runtime-guide";
import { placeBelow } from "@/lib/browser";

const SNAPSHOT_HELP =
  "Rankings read this dated list of US-listed operating companies (the universe snapshot); lookups do not need it.";
const ANALYSIS_HELP =
  "What your follow-ups change: the companies, metrics and period on screen. × removes one; + adds one.";

/**
 * The runtime, the ranking snapshot and the turn counter as compact pills, then
 * the active analysis as chips a follow-up can edit. One row on a phone.
 */
export function StatusLine({
  runtime,
  runtimeBanner,
  guide = null,
  snapshot,
  chips,
  edits = [],
  actions = null,
  editable = false,
  onEdit,
  onDraft,
  turns,
}: {
  runtime: RuntimeKind | null;
  /** null while loading; empty when the storefront copy could not be loaded. */
  runtimeBanner: string | null;
  /** What each runtime answers from; null hides the explainer. */
  guide?: Guide | null;
  snapshot: { banner: string; stale: boolean } | null;
  chips: string[];
  /** Each chip's kind and the follow-up its × sends. */
  edits?: ChipEdit[];
  /** The "+" menu's follow-ups. */
  actions?: QuickActions | null;
  /** A follow-up can be sent now. */
  editable?: boolean;
  onEdit?: (message: string) => void;
  /** Puts a half-written follow-up ("add ") in the question box. */
  onDraft?: (text: string) => void;
  /** null hides the counter: no thread yet, or nothing asked on it. */
  turns: { count: number; max: number } | null;
}) {
  // "Live runtime — figures pulled …": the name is the pill; the detail is its title.
  const [runtimeName] = splitBanner(runtimeBanner ?? "");
  const live = runtime === "live";
  const shortName = runtime === "live" ? "Live" : runtime === "recorded" ? "Recorded" : "";
  return (
    // A landmark of its own, so the runtime and snapshot lines are not stray page content.
    <section aria-label="Conversation status" className="border-b border-border bg-surface sm:tall:sticky sm:top-14 sm:z-20">
      <div className="mx-auto flex max-w-4xl items-center gap-2 px-4 py-1.5 text-[12px] leading-5 text-subtle sm:gap-2.5 sm:px-6 2xl:max-w-5xl min-[1920px]:max-w-6xl">
        {runtimeBanner === null ? (
          <span className="shimmer animate-shimmer h-5 w-56 max-w-full rounded-full" aria-hidden />
        ) : runtimeBanner === "" ? null : (
          <>
            <span
              className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-border bg-surface-2/70 px-2.5 py-0.5 font-medium text-muted"
              title={runtimeBanner}
            >
              <Dot live={live} />
              <span className="sm:hidden">{shortName || runtimeName}</span>
              <span className="hidden sm:inline">{runtimeName}</span>
            </span>
            {guide && (
              <span className="hidden sm:inline-flex">
                <RuntimeGuide guide={guide} runtime={runtime} />
              </span>
            )}
          </>
        )}
        {snapshot && (
          <span
            title={SNAPSHOT_HELP}
            className={cn(
              "hidden shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-0.5 sm:inline-flex",
              snapshot.stale ? "border-warning/30 bg-warning-soft text-warning" : "border-border text-subtle",
            )}
          >
            <CalendarClock className="size-3.5 shrink-0" aria-hidden />
            <span className="whitespace-nowrap">{snapshot.banner}</span>
          </span>
        )}
        {turns && (
          <span
            role="group"
            data-turns={turns.count}
            className="num shrink-0 text-subtle sm:ml-auto"
            aria-label="Turns used"
            title={`A conversation holds up to ${turns.max} questions and follow-ups. Start over for a fresh one.`}
          >
            <span aria-hidden className="mr-2 text-border-strong sm:hidden">
              ·
            </span>
            <span className="sm:hidden">{`${turns.count}/${turns.max}`}</span>
            <span className="hidden sm:inline">{turnCounterLabel(turns.count, turns.max)}</span>
          </span>
        )}
        {guide && (
          // A phone's one row ends with ⓘ: the runtimes and the snapshot behind one button.
          <span className={cn("inline-flex sm:hidden", !turns && "ml-auto")}>
            {turns && (
              <span aria-hidden className="mr-1 text-border-strong">
                ·
              </span>
            )}
            <RuntimeGuide guide={guide} runtime={runtime} compact note={snapshot?.banner ?? null} />
          </span>
        )}
      </div>
      {chips.length > 0 && (
        <ActiveAnalysis
          chips={chips}
          edits={edits}
          actions={actions}
          editable={editable && Boolean(onEdit)}
          onEdit={onEdit}
          onDraft={onDraft}
        />
      )}
    </section>
  );
}

function Dot({ live }: { live: boolean }) {
  return (
    <span
      aria-hidden
      className={cn(
        "size-1.5 shrink-0 rounded-full",
        live ? "bg-positive shadow-[0_0_0_3px] shadow-positive/20" : "bg-primary shadow-[0_0_0_3px] shadow-primary/20",
      )}
    />
  );
}

function ActiveAnalysis({
  chips,
  edits,
  actions,
  editable,
  onEdit,
  onDraft,
}: {
  chips: string[];
  edits: ChipEdit[];
  actions: QuickActions | null;
  editable: boolean;
  onEdit?: (message: string) => void;
  onDraft?: (text: string) => void;
}) {
  const byLabel = new Map(edits.map((edit) => [edit.label, edit]));
  const offered = actions && (actions.company.length || actions.metric.length || actions.period.length);
  return (
    <div className="border-t border-border/60">
      <div className="mx-auto flex max-w-4xl items-center gap-2 overflow-x-auto px-4 py-1.5 [scrollbar-width:none] sm:px-6 2xl:max-w-5xl min-[1920px]:max-w-6xl">
        <span
          className="shrink-0 cursor-help text-[10px] font-medium uppercase tracking-[0.08em] text-subtle"
          title={ANALYSIS_HELP}
        >
          Now showing
        </span>
        <ul className="flex shrink-0 items-center gap-1.5" aria-label="Active analysis">
          {chips.map((chip) => {
            const edit = byLabel.get(chip);
            const remove = edit?.remove ?? null;
            const keep = editable && !remove ? (edit?.keep ?? undefined) : undefined;
            return (
              <li
                key={chip}
                title={keep}
                className="inline-flex h-6 items-center rounded-md border border-border bg-surface-2 pl-1.5 pr-1.5 text-[11.5px] text-fg has-[button]:pr-0.5"
              >
                {chip}
                {remove && editable && (
                  <button
                    type="button"
                    onClick={() => onEdit?.(remove)}
                    aria-label={`Remove ${chip}`}
                    title={`Ask: “${remove}”`}
                    className="ml-1 inline-flex size-5 items-center justify-center rounded text-subtle transition-colors hover:bg-surface-3 hover:text-fg"
                  >
                    <X className="size-3" aria-hidden />
                  </button>
                )}
              </li>
            );
          })}
        </ul>
        {offered && editable ? <AddMenu actions={actions} onEdit={onEdit} onDraft={onDraft} /> : null}
      </div>
    </div>
  );
}

const GROUPS: { key: keyof QuickActions; title: string; draft?: string }[] = [
  { key: "company", title: "Add a company", draft: "Another company…" },
  { key: "metric", title: "Add a metric", draft: "Another metric…" },
  { key: "period", title: "Change the period" },
];

/** "+": a native popover of follow-ups the planner reads; Escape or a click elsewhere closes it. */
function AddMenu({
  actions,
  onEdit,
  onDraft,
}: {
  actions: QuickActions;
  onEdit?: (message: string) => void;
  onDraft?: (text: string) => void;
}) {
  const id = useId();
  const button = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);

  function place(event: ToggleEvent<HTMLDivElement>) {
    if (event.newState !== "open" || !button.current) return;
    placeBelow(event.currentTarget, button.current.getBoundingClientRect(), 288, 6);
  }

  function choose(run: () => void) {
    panel.current?.hidePopover();
    run();
  }

  return (
    <>
      <button
        ref={button}
        type="button"
        popoverTarget={id}
        aria-label="Add to the analysis"
        title="Add a company or a metric, or change the period"
        className="inline-flex h-6 shrink-0 items-center gap-1 rounded-md border border-dashed border-border-strong px-1.5 text-[11.5px] text-muted transition-colors hover:border-primary/60 hover:text-primary"
      >
        <Plus className="size-3" aria-hidden />
        <span className="hidden sm:inline">Add</span>
      </button>
      <div
        ref={panel}
        id={id}
        popover="auto"
        role="menu"
        aria-label="Add to the analysis"
        onBeforeToggle={place}
        className="fixed inset-auto m-0 max-h-[calc(100dvh-8rem)] overflow-y-auto rounded-xl border border-border-strong bg-surface p-1.5 text-[13px] text-fg shadow-xl shadow-black/25"
      >
        {GROUPS.map(({ key, title, draft }) =>
          actions[key].length === 0 ? null : (
            <div key={key} role="group" aria-label={title} className="py-1 [&+&]:border-t [&+&]:border-border">
              <div className="px-2 pb-1 pt-0.5 text-[10.5px] font-medium uppercase tracking-[0.08em] text-subtle">{title}</div>
              {actions[key].map((action: QuickAction) => (
                <button
                  key={action.message}
                  type="button"
                  role="menuitem"
                  onClick={() => choose(() => onEdit?.(action.message))}
                  className="flex w-full items-center justify-between gap-3 rounded-md px-2 py-1.5 text-left hover:bg-surface-2 focus-visible:bg-surface-2 focus-visible:outline-none"
                >
                  {action.label}
                  <span className="truncate text-[11.5px] text-subtle">{action.message}</span>
                </button>
              ))}
              {draft && onDraft && (
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => choose(() => onDraft("add "))}
                  className="flex w-full items-center rounded-md px-2 py-1.5 text-left text-muted hover:bg-surface-2 hover:text-fg focus-visible:bg-surface-2 focus-visible:outline-none"
                >
                  {draft}
                </button>
              )}
            </div>
          ),
        )}
      </div>
    </>
  );
}
