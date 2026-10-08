import { ArrowRight, ChevronDown, FileDiff } from "lucide-react";
import { useMemo, useState } from "react";
import { changedSentences, splitChanges } from "@/lib/diff-view";
import { cn, safeHref } from "@/lib/format";
import type { DisplayDisclosure } from "@/lib/types";
import { wordDiff, type DiffPiece, type UnifiedPiece } from "@/lib/word-diff";
import { useRegionName } from "./answer-scope";
import { Badge, ExternalLink, FilingButton, SectionLabel, type Tone } from "./ui";

const KIND_TONE: Record<string, Tone> = {
  added: "positive",
  removed: "negative",
  changed: "warning",
};

// Changes shown before "Show more": a 10-Q pair can differ in a hundred paragraphs.
const FIRST_CHANGES = 4;

/**
 * Each changed 10-Q paragraph: those that move a figure first, larger before
 * smaller, and edits that only reword folded into one row. Side by side on a
 * wide screen; one merged paragraph, cut to the changed sentences, on a phone.
 */
export function FilingChanges({ items }: { items: DisplayDisclosure[] }) {
  const { older_accession: older, newer_accession: newer } = items[0];
  const { substantive, wording } = useMemo(() => splitChanges(items), [items]);
  const sections = new Set(items.map((item) => item.section_label)).size;
  const [open, setOpen] = useState(false);
  const shown = open ? substantive : substantive.slice(0, FIRST_CHANGES);
  const hidden = substantive.length - shown.length;
  const name = useRegionName("Filing changes");
  return (
    <section aria-label={name} className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5">
        <SectionLabel>
          {`${items.length} ${items.length === 1 ? "change" : "changes"} in ${sections} ${
            sections === 1 ? "section" : "sections"
          }`}
        </SectionLabel>
        {older && newer && (
          <div className="num flex items-center gap-1.5 text-[11px] text-subtle">
            <span>{older}</span>
            <ArrowRight className="size-3 shrink-0" aria-label="to" />
            <span className="text-muted">{newer}</span>
          </div>
        )}
      </div>
      {shown.map((item, index) => (
        <FilingChange key={index} item={item} />
      ))}
      {hidden > 0 && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="flex w-full items-center justify-center gap-1.5 rounded-xl border border-dashed border-border-strong px-4 py-2.5 text-xs font-medium text-muted transition-colors hover:border-primary/50 hover:bg-primary-soft hover:text-fg"
        >
          <ChevronDown className="size-3.5" aria-hidden />
          {`Show ${hidden} more ${hidden === 1 ? "change" : "changes"}`}
        </button>
      )}
      {wording.length > 0 && <WordingEdits items={wording} />}
    </section>
  );
}

/** Rewordings with no figure changed: one row that opens to the edits. */
function WordingEdits({ items }: { items: DisplayDisclosure[] }) {
  return (
    <details className="group/wording overflow-hidden rounded-xl border border-border bg-surface">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-[13px] text-fg transition-colors hover:bg-surface-2/60 sm:px-5 [&::-webkit-details-marker]:hidden">
        <FileDiff className="size-4 shrink-0 text-subtle" aria-hidden />
        {`${items.length} wording-only ${items.length === 1 ? "edit" : "edits"}`}
        <span className="hidden text-[12px] text-subtle sm:inline">· no figure changed</span>
        <ChevronDown className="ml-auto size-4 shrink-0 text-subtle transition-transform group-open/wording:rotate-180" aria-hidden />
      </summary>
      <div className="space-y-3 border-t border-border bg-surface-2/30 p-3">
        {items.map((item, index) => (
          <FilingChange key={index} item={item} />
        ))}
      </div>
    </details>
  );
}

// Characters either side may run to before the pair is clamped with "Show full text".
const LONG_CHANGE = 1200;

function FilingChange({ item }: { item: DisplayDisclosure }) {
  const long = Math.max(item.before_text.length, item.after_text.length) > LONG_CHANGE;
  const [expanded, setExpanded] = useState(false);
  const clamped = long && !expanded;
  // Within a changed paragraph, the words that went and the words that came.
  const diff = useMemo(
    () => (item.change_kind === "changed" ? wordDiff(item.before_text, item.after_text) : null),
    [item.change_kind, item.before_text, item.after_text],
  );
  return (
    <article
      aria-label={`${item.section_label}, ${item.change_kind}`}
      className="overflow-hidden rounded-xl border border-border bg-surface"
    >
      <header className="flex items-center justify-between gap-3 border-b border-border px-4 py-2.5 sm:px-5">
        <h3 className="flex min-w-0 items-start gap-2 text-[13px] font-medium leading-snug text-fg">
          <FileDiff className="mt-px size-4 shrink-0 text-primary" aria-hidden />
          {item.subsection ? (
            // The heading the paragraph sits under says more than the section's name.
            <span className="min-w-0 text-pretty">
              {item.subsection}
              <span className="ml-2 text-[11.5px] font-normal text-subtle">{item.section_label}</span>
            </span>
          ) : (
            <span className="min-w-0 text-pretty">{item.section_label}</span>
          )}
        </h3>
        <Badge tone={KIND_TONE[item.change_kind] ?? "neutral"} className="shrink-0 capitalize">
          {item.change_kind}
        </Badge>
      </header>
      <Unified item={item} pieces={diff?.unified ?? null} />
      <div className="hidden md:grid md:grid-cols-2">
        <FilingSide
          label="Previous filing"
          text={item.before_text}
          pieces={diff?.before}
          href={item.older_url}
          link="Open previous filing"
          clamped={clamped}
        />
        <FilingSide
          current
          label="Current filing"
          text={item.after_text}
          pieces={diff?.after}
          href={item.newer_url}
          link="Open current filing"
          clamped={clamped}
        />
      </div>
      {long && (
        <button
          type="button"
          aria-expanded={expanded}
          onClick={() => setExpanded((open) => !open)}
          className="hidden w-full items-center justify-center gap-1.5 border-t border-border px-4 py-2 text-xs font-medium text-muted transition-colors hover:bg-surface-2 hover:text-fg md:flex"
        >
          <ChevronDown className={cn("size-3.5 transition-transform", expanded && "rotate-180")} aria-hidden />
          {expanded ? "Show less" : "Show full text"}
        </button>
      )}
    </article>
  );
}

/**
 * A phone's view: one paragraph with the old words struck in red and the new
 * in green, cut to the sentences that changed until the reader asks for all.
 */
function Unified({ item, pieces }: { item: DisplayDisclosure; pieces: UnifiedPiece[] | null }) {
  const [full, setFull] = useState(false);
  const text = item.change_kind === "removed" ? item.before_text : item.after_text;
  const kind = item.change_kind;
  const whole: UnifiedPiece[] = useMemo(
    () => pieces ?? (text ? [{ text, kind: kind === "removed" ? "removed" : kind === "added" ? "added" : "same" }] : []),
    [pieces, text, kind],
  );
  const { sentences, omitted } = useMemo(() => changedSentences(whole), [whole]);
  // An added or removed paragraph is all change: clamp it by length instead.
  const allChanged = !pieces;
  const cut = !full && (allChanged ? text.length > 420 : omitted && sentences.length > 0);
  return (
    <div className="md:hidden">
      <div className="px-4 py-3">
        <p
          className={cn(
            "whitespace-pre-wrap break-words text-[14px] leading-[1.7] text-fg",
            cut && allChanged && "line-clamp-6",
          )}
        >
          {cut && !allChanged
            ? sentences.map((sentence, index) => (
                <span key={index}>
                  <span className="text-subtle">… </span>
                  <Runs pieces={sentence} strike />
                </span>
              ))
            : <Runs pieces={whole} strike={!allChanged} />}
          {cut && !allChanged && <span className="text-subtle"> …</span>}
        </p>
        {(cut || full) && (
          <button
            type="button"
            aria-expanded={full}
            onClick={() => setFull((open) => !open)}
            className="mt-2 inline-flex items-center gap-1 rounded text-xs font-medium text-primary underline-offset-4 hover:underline"
          >
            <ChevronDown className={cn("size-3.5 transition-transform", full && "rotate-180")} aria-hidden />
            {full ? "Show only what changed" : "Show full paragraph"}
          </button>
        )}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 border-t border-border bg-surface-2/35 px-4 py-2.5 text-xs">
        {safeHref(item.older_url) && (
          <ExternalLink href={item.older_url} className="gap-0.5 font-medium">
            Previous filing
          </ExternalLink>
        )}
        {safeHref(item.newer_url) && (
          <ExternalLink href={item.newer_url} className="gap-0.5 font-medium">
            Current filing
          </ExternalLink>
        )}
      </div>
    </div>
  );
}

/** `strike`: words gone from a paragraph that stays; a paragraph gone whole is tinted, not struck, to stay readable. */
function Runs({ pieces, strike = false }: { pieces: UnifiedPiece[]; strike?: boolean }) {
  return (
    <>
      {pieces.map((piece, index) =>
        piece.kind === "same" ? (
          <span key={index}>{piece.text}</span>
        ) : piece.kind === "added" ? (
          <ins key={index} className="rounded-[3px] bg-positive-soft text-fg no-underline ring-1 ring-positive/25">
            {piece.text}
          </ins>
        ) : (
          <del
            key={index}
            className={cn(
              "rounded-[3px] bg-negative-soft ring-1 ring-negative/25",
              strike ? "text-muted decoration-negative/60" : "text-fg no-underline",
            )}
          >
            {piece.text}
          </del>
        ),
      )}
    </>
  );
}

function FilingSide({
  label,
  text,
  pieces,
  href,
  link,
  current = false,
  clamped = false,
}: {
  label: string;
  text: string;
  /** The text cut into kept and changed words, when the pair was compared. */
  pieces?: DiffPiece[];
  href: string;
  link: string;
  current?: boolean;
  /** Long text is cut to a fixed height, fading out, until the reader expands it. */
  clamped?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex min-w-0 flex-col border-border",
        current ? "border-t md:border-l md:border-t-0" : "bg-surface-2/35",
      )}
    >
      <div className="px-4 pt-3.5 sm:px-5">
        <div className="flex items-center gap-2 text-[10.5px] font-medium uppercase tracking-[0.08em] text-subtle">
          <span
            aria-hidden
            className={cn(
              "size-1.5 rounded-full",
              current ? "bg-primary shadow-[0_0_0_3px] shadow-primary/15" : "bg-subtle/60",
            )}
          />
          {label}
        </div>
      </div>
      <div
        className={cn(
          "flex-1 px-4 py-3 sm:px-5",
          clamped &&
            "max-h-[22rem] overflow-hidden [mask-image:linear-gradient(to_bottom,black_75%,transparent)]",
        )}
      >
        {text ? (
          // Filing prose, as filed: "1." or "*" in a 10-Q is not markup. Changed
          // words are marked by colour alone (red here, green on the current
          // side), never struck, so the old wording stays easy to read.
          <p className={cn("whitespace-pre-wrap break-words text-[14px] leading-[1.7] text-fg", !current && "text-muted")}>
            {pieces ? <Runs pieces={pieces.map((piece) => sided(piece, current))} /> : text}
          </p>
        ) : (
          <p className="text-[13px] italic text-subtle">Not in this filing.</p>
        )}
      </div>
      <div className="px-4 pb-4 sm:px-5">
        <FilingButton href={href} label={link} emphasis={current} />
      </div>
    </div>
  );
}

/** One side's piece as a run: a changed word is new on the current side and gone on the previous. */
function sided(piece: DiffPiece, current: boolean): UnifiedPiece {
  return { text: piece.text, kind: !piece.changed ? "same" : current ? "added" : "removed" };
}
