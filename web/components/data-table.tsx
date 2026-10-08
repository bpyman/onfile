"use client";

import { ArrowDown, ArrowUp, ArrowUpDown, RotateCcw, Table2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { cn, safeHref } from "@/lib/format";
import type { ShownTable } from "@/lib/pivot";
import { nextSort, type TableSort } from "@/lib/table-sort";
import { hasProvenance, soleCompany, tableColumns, type TableColumn, type TableMode } from "@/lib/table-view";
import { useRegionName } from "./answer-scope";
import { CopyButton } from "./copy-button";
import { useInspect } from "./inspect-context";
import { Badge, ExternalLink } from "./ui";

const MODES: { mode: TableMode; label: string }[] = [
  { mode: "compact", label: "Compact" },
  { mode: "full", label: "Full" },
];

// A one-row table with this many amounts reads better as a grid on a phone.
const GRID_VALUES = 3;

/**
 * The answer's rows as the server wrote them; the full view adds provenance.
 * A column header sorts the rows; the answer holds the sort so its chart can
 * follow it. A figure with a source opens it in the inspector.
 */
export function DataTable({
  table,
  sort = null,
  rowOrder = null,
  onSort,
  bare = false,
  pivoted = false,
}: {
  table: ShownTable;
  sort?: TableSort | null;
  /** The rows in the sort's order, as the answer computed them; the server's order when absent. */
  rowOrder?: number[] | null;
  onSort?: (sort: TableSort | null) => void;
  /** Inside the answer card: no border of its own. */
  bare?: boolean;
  /** Quarters down, companies across. */
  pivoted?: boolean;
}) {
  const [mode, setMode] = useState<TableMode>("compact");
  const columns = tableColumns(table, mode);
  const count = table.rows.length;
  const sortable = Boolean(onSort) && count > 1;
  const order = rowOrder ?? table.rows.map((_, index) => index);
  const sortedBy = sort ? columns.find((column) => column.key === sort.key)?.header : undefined;
  const name = useRegionName("Answer table");
  const values = columns.filter((column) => column.kind === "value");
  // The first column a row is known by (not its rank) stays in view as amounts scroll.
  const pinned = columns.findIndex((column) => column.kind !== "rank");
  const grid = count === 1 && values.length >= GRID_VALUES;
  const dated = columns.find((column) => column.kind === "date");
  const { ref: scrollRef, more, update } = useScrollFade();
  return (
    <section
      aria-label={name}
      className={cn("overflow-hidden", !bare && "rounded-xl border border-border bg-surface")}
    >
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-2.5 sm:px-5">
        <div className="flex min-w-0 items-center gap-2 text-[13px] font-medium text-fg">
          <Table2 className="size-4 shrink-0 text-primary" aria-hidden />
          Table
          {soleCompany(table) && <span className="truncate font-normal text-muted">{soleCompany(table)}</span>}
          <span className={cn("shrink-0 text-[11px] font-normal tabular-nums text-subtle", grid && "max-sm:hidden")}>
            {pivoted ? "quarters × companies" : count === 1 ? "1 row" : `${count} rows`}
          </span>
          {grid && dated && (
            <span className="truncate text-[11px] font-normal text-subtle sm:hidden">
              {`${dated.header} ${table.rows[0][dated.index] ?? ""}`}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {sortable && sort && (
            <button
              type="button"
              onClick={() => onSort?.(null)}
              className="inline-flex h-7 items-center gap-1 rounded-md px-2 text-[11.5px] font-medium text-muted transition-colors hover:bg-surface-2 hover:text-fg"
              title={sortedBy ? `Sorted by ${sortedBy}` : undefined}
            >
              <RotateCcw className="size-3" aria-hidden />
              Original order
            </button>
          )}
          {hasProvenance(table) && (
            <div
              role="radiogroup"
              aria-label="Table columns"
              className="flex h-7 items-center rounded-lg border border-border bg-surface-2 p-0.5"
            >
              {MODES.map(({ mode: option, label }) => {
                const active = option === mode;
                return (
                  <button
                    key={option}
                    type="button"
                    role="radio"
                    aria-checked={active}
                    onClick={() => setMode(option)}
                    className={cn(
                      "inline-flex h-full items-center rounded-md px-2.5 text-[11.5px] font-medium transition-colors",
                      active ? "bg-surface text-fg shadow-sm ring-1 ring-border-strong" : "text-muted hover:text-fg",
                    )}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </header>
      {grid && <FigureGrid table={table} columns={values} />}
      {/* relative: keeps sr-only text inside the scroller instead of widening the page. */}
      <div className={cn("relative", grid && "hidden sm:block")}>
        <div ref={scrollRef} onScroll={update} className="overflow-x-auto overscroll-x-contain">
          <table className="w-full border-collapse text-[13px]">
            <thead>
              <tr>
                {columns.map((column, index) => (
                  <th
                    key={column.key}
                    scope="col"
                    aria-sort={
                      sortable && column.kind !== "filing"
                        ? sort?.key === column.key
                          ? sort.direction
                          : "none"
                        : undefined
                    }
                    className={cn(
                      "whitespace-nowrap bg-surface-2 px-3 py-2 align-bottom text-[10.5px] font-medium uppercase tracking-[0.08em] text-subtle first:pl-4 last:pr-4 sm:first:pl-5 sm:last:pr-5",
                      column.numeric ? "text-right" : "text-left",
                      column.kind === "rank" && "hidden w-px pr-1 sm:table-cell",
                      column.kind === "filing" && "w-px text-right",
                      index === pinned && STICKY,
                    )}
                  >
                    {column.kind === "filing" ? (
                      <span className="sr-only">{column.header}</span>
                    ) : sortable ? (
                      <SortButton
                        column={column}
                        sort={sort}
                        onClick={() => onSort?.(nextSort(table, sort, column.key))}
                      />
                    ) : (
                      <Header column={column} />
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {order.map((rowIndex) => (
                <tr key={rowIndex} className="group/row border-t border-border">
                  {columns.map((column, index) => (
                    <td
                      key={column.key}
                      className={cn(
                        "whitespace-nowrap bg-surface px-3 py-2.5 align-middle transition-colors first:pl-4 last:pr-4 group-hover/row:bg-[color-mix(in_srgb,var(--surface-2)_60%,var(--surface))] sm:first:pl-5 sm:last:pr-5",
                        column.numeric && "text-right",
                        column.kind === "rank" && "hidden pr-1 sm:table-cell",
                        column.kind === "filing" && "text-right",
                        index === pinned && STICKY,
                      )}
                    >
                      <Cell
                        column={column}
                        row={table.rows[rowIndex]}
                        evidence={table.evidence?.[rowIndex]?.[column.index] ?? null}
                        title={table.titles?.[rowIndex]?.[column.index] ?? undefined}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {/* More columns to the right: a fade says the table scrolls. */}
        <span
          aria-hidden
          className={cn(
            "pointer-events-none absolute inset-y-0 right-0 w-10 bg-gradient-to-l from-surface to-transparent transition-opacity",
            more ? "opacity-100" : "opacity-0",
          )}
        />
      </div>
    </section>
  );
}

// The first column stays put while the amounts scroll beside it.
// On a phone the rank is the bar chart's to show, and the company stays put.
const STICKY = "max-sm:sticky max-sm:left-0 max-sm:z-[1] max-sm:shadow-[1px_0_0_var(--border)]";

/** Whether a horizontal scroller has more to show on its right. */
function useScrollFade() {
  const ref = useRef<HTMLDivElement | null>(null);
  const [more, setMore] = useState(false);
  const update = useCallback(() => {
    const box = ref.current;
    if (box) setMore(box.scrollLeft + box.clientWidth < box.scrollWidth - 2);
  }, []);
  useEffect(() => {
    const box = ref.current;
    if (!box) return;
    const observer = new ResizeObserver(update);
    observer.observe(box);
    return () => observer.disconnect();
  }, [update]);
  return { ref, more, update };
}

/** One company's quarter as label and amount pairs, two to a row (a phone's overview). */
function FigureGrid({ table, columns }: { table: ShownTable; columns: TableColumn[] }) {
  const row = table.rows[0];
  return (
    <dl className="grid grid-cols-2 sm:hidden">
      {columns.map((column, index) => (
        <div
          key={column.key}
          className={cn(
            "min-w-0 border-border px-4 py-3",
            index % 2 === 1 && "border-l",
            index >= 2 && "border-t",
            // An odd last figure spans the row rather than leave half of it empty.
            index === columns.length - 1 && index % 2 === 0 && "col-span-2",
          )}
        >
          <dt className="truncate text-[10.5px] font-medium uppercase tracking-[0.08em] text-subtle" title={column.header}>
            {column.header}
          </dt>
          <dd className="mt-1 text-[15px]">
            <Cell column={column} row={row} evidence={table.evidence?.[0]?.[column.index] ?? null} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

function Header({ column }: { column: TableColumn }) {
  return column.kind === "value" ? (
    // A long metric name wraps rather than pushing amounts out of view.
    <span className="inline-block max-w-[6.5rem] whitespace-normal leading-snug">{column.header}</span>
  ) : (
    <>{column.header}</>
  );
}

function SortButton({
  column,
  sort,
  onClick,
}: {
  column: TableColumn;
  sort: TableSort | null;
  onClick: () => void;
}) {
  const active = sort?.key === column.key;
  const Icon = !active ? ArrowUpDown : sort.direction === "ascending" ? ArrowUp : ArrowDown;
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "group -mx-1 inline-flex items-center gap-1 rounded px-1 uppercase tracking-[0.08em] transition-colors hover:text-fg",
        column.numeric && "flex-row-reverse",
        active && "text-fg",
      )}
    >
      <Header column={column} />
      <Icon
        className={cn("size-3 shrink-0", active ? "text-primary" : "opacity-40 group-hover:opacity-80 group-focus-visible:opacity-80")}
        aria-hidden
      />
    </button>
  );
}

function Cell({
  column,
  row,
  evidence = null,
  title,
}: {
  column: TableColumn;
  row: string[];
  /** The figure's index in the answer's evidence. */
  evidence?: number | null;
  /** The cell's own company and quarter, when its row stands for several. */
  title?: string;
}) {
  const inspect = useInspect();
  const value = row[column.index] ?? "";
  switch (column.kind) {
    case "rank":
      return <span className="num text-subtle">{value}</span>;
    case "company": {
      const ticker = column.tickerIndex === undefined ? "" : row[column.tickerIndex];
      return (
        <span className="flex min-w-0 items-center gap-2.5" title={value}>
          {ticker ? (
            <span className="num inline-flex h-5 min-w-11 shrink-0 items-center justify-center rounded border border-border-strong bg-surface-2 px-1.5 text-[10.5px] font-semibold text-fg">
              {ticker}
            </span>
          ) : (
            // Keeps names aligned when a row has no ticker.
            column.tickerIndex !== undefined && <span aria-hidden className="w-11 shrink-0" />
          )}
          {/* A phone shows the ticker alone, so the amounts fit; the name is its title. */}
          <span className={cn("max-w-[6.5rem] truncate text-fg sm:max-w-[12rem]", ticker && "sr-only sm:not-sr-only")}>
            {value}
          </span>
        </span>
      );
    }
    case "value":
      if (!value) {
        return (
          <span className="text-subtle" aria-label="No value">
            —
          </span>
        );
      }
      if (inspect && evidence !== null) {
        return (
          <button
            type="button"
            onClick={() => inspect(evidence)}
            title={title ? `${title}. Show its source` : "Show its source"}
            className="rounded-sm font-medium tabular-nums text-fg underline decoration-border-strong decoration-dotted underline-offset-4 transition-colors hover:text-primary hover:decoration-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            {value}
          </button>
        );
      }
      return (
        <span className="font-medium tabular-nums text-fg" title={title}>
          {value}
        </span>
      );
    case "date":
      return <span className="tabular-nums text-muted">{value}</span>;
    case "identifier":
      return value ? (
        <span className="inline-flex items-center gap-0.5">
          <span className="num text-muted">{value}</span>
          <CopyButton value={value} label={column.header} />
        </span>
      ) : null;
    case "code":
      return (
        <span className="num block max-w-[18rem] truncate text-[12px] text-muted" title={value}>
          {value}
        </span>
      );
    case "reason":
      return value ? <Badge tone="warning">{value}</Badge> : null;
    case "filing":
      return safeHref(value) ? (
        <ExternalLink href={value} className="gap-0.5 rounded text-xs font-medium">
          Filing
        </ExternalLink>
      ) : null;
    default:
      return <span className="text-fg">{value}</span>;
  }
}
