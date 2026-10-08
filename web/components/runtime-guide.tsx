"use client";

import { CalendarClock, CircleHelp, Database, Info, Radio } from "lucide-react";
import { cn } from "@/lib/format";
import type { RuntimeGuide as Guide, RuntimeKind } from "@/lib/types";
import { placeBelow, useAnchoredPopover } from "@/lib/browser";

const PANEL_WIDTH = 352;
const GUTTER = 12;

/**
 * "How runtimes differ": what Recorded and Live each answer from. A native
 * popover, so Escape and a click elsewhere close it; it opens under its button.
 */
export function RuntimeGuide({
  guide,
  runtime,
  compact = false,
  note = null,
}: {
  guide: Guide;
  runtime: RuntimeKind | null;
  /** A phone's status row: the button is an ⓘ alone. */
  compact?: boolean;
  /** A line the panel ends with: the ranking snapshot's date, when the row has no room for it. */
  note?: string | null;
}) {
  const { id, button, onBeforeToggle } = useAnchoredPopover((panel, anchor) =>
    placeBelow(panel, anchor, PANEL_WIDTH, 8, GUTTER),
  );

  return (
    <>
      <button
        ref={button}
        type="button"
        popoverTarget={id}
        aria-label={compact ? "How runtimes differ" : undefined}
        className={cn(
          "inline-flex shrink-0 items-center gap-1 rounded-md text-subtle underline-offset-2 transition-colors hover:text-fg hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
          compact ? "size-6 justify-center" : "px-1",
        )}
      >
        {compact ? <Info className="size-4" aria-hidden /> : <CircleHelp className="size-3.5" aria-hidden />}
        {!compact && <span>How runtimes differ</span>}
      </button>
      <div
        id={id}
        popover="auto"
        role="dialog"
        aria-label="How runtimes differ"
        onBeforeToggle={onBeforeToggle}
        className="fixed inset-auto m-0 max-h-[calc(100dvh-6rem)] overflow-y-auto rounded-xl border border-border-strong bg-surface p-4 text-[12.5px] leading-relaxed text-muted shadow-xl shadow-black/25"
      >
        <div className="space-y-3.5">
          {guide.runtimes.map((item) => {
            const Icon = item.kind === "live" ? Radio : Database;
            const current = item.kind === runtime;
            return (
              <section key={item.kind}>
                <h3 className="flex items-center gap-1.5 text-[13px] font-medium text-fg">
                  <Icon
                    className={cn("size-3.5", item.kind === "live" ? "text-positive" : "text-primary")}
                    aria-hidden
                  />
                  {item.name}
                  {current && (
                    <span className="rounded bg-surface-2 px-1.5 py-px text-[10.5px] font-medium text-subtle">
                      This conversation
                    </span>
                  )}
                </h3>
                <ul className="mt-1.5 list-disc space-y-1 pl-5 marker:text-subtle">
                  {item.points.map((point) => (
                    <li key={point}>{point}</li>
                  ))}
                </ul>
              </section>
            );
          })}
          {guide.footer && <p className="border-t border-border pt-3 text-subtle">{guide.footer}</p>}
          {note && (
            <p className="flex items-start gap-1.5 text-subtle" title="Rankings read this dated list of US-listed operating companies; lookups do not need it.">
              <CalendarClock className="mt-[3px] size-3.5 shrink-0" aria-hidden />
              {note}
            </p>
          )}
        </div>
      </div>
    </>
  );
}
