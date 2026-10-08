import type { BarChartSpec, LineChartSpec } from "./types";

/**
 * Chart rows built from the server's chart records. Amounts shown as text
 * (tooltips, end labels, bar labels) are the server's strings; numbers here
 * only place marks (ADR 0006).
 */

/**
 * Categorical slots in their validated order (globals.css). A series past the
 * last slot is drawn muted rather than given a generated hue.
 */
export const SERIES_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
  "var(--chart-6)",
  "var(--chart-7)",
  "var(--chart-8)",
] as const;

export interface LineSeries {
  /** Positional data key: company names such as "Apple Inc." read as paths. */
  key: string;
  name: string;
  /** The short name an end label or a crowded tooltip uses: the ticker. */
  label: string;
  color: string;
}

export interface LineRow {
  period: string;
  /** The period end as epoch milliseconds (UTC), or null when the server sent no date. */
  time: number | null;
  amounts: Record<string, string>;
  /** Each series' evidence index at this period. */
  evidence: Record<string, number>;
  /** Series whose point here is derived (†), drawn hollow. */
  derived: string[];
  /** Series whose latest point is in this row. */
  last?: string[];
  [series: string]: string | number | null | Record<string, string> | Record<string, number> | string[] | undefined;
}

export function lineSeries(spec: LineChartSpec): LineSeries[] {
  return spec.series.map((name, index) => ({
    key: `s${index}`,
    name,
    label: spec.series_labels?.[index] || name,
    color: SERIES_COLORS[index] ?? "var(--chart-muted)",
  }));
}

export function lineRows(spec: LineChartSpec): LineRow[] {
  const series = lineSeries(spec);
  const lastIndex = new Map<string, number>();
  const rows = spec.records.map((record, index) => {
    const row: LineRow = {
      period: spec.period_labels[index] ?? String(record.Period ?? ""),
      time: periodTime(record.Period),
      amounts: {},
      evidence: {},
      derived: [],
    };
    for (const { key, name } of series) {
      const evidence = spec.evidence?.[index]?.[name];
      if (typeof evidence === "number") row.evidence[key] = evidence;
      if (spec.derived?.[index]?.includes(name)) row.derived.push(key);
      const value = record[name];
      row[key] = typeof value === "number" && Number.isFinite(value) ? value : null;
      const amount = spec.amounts[index]?.[name];
      if (amount) row.amounts[key] = amount;
      if (row[key] !== null) lastIndex.set(key, index);
    }
    return row;
  });
  for (const { key } of series) {
    const index = lastIndex.get(key);
    if (index === undefined) continue;
    (rows[index].last ??= []).push(key);
  }
  return rows;
}

function periodTime(value: unknown): number | null {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const time = Date.parse(`${value}T00:00:00Z`);
  return Number.isFinite(time) ? time : null;
}

const DAY = 86_400_000;

/**
 * Whether the rows interleave companies on different fiscal calendars (Nvidia's
 * quarter ending July 26 beside AMD's ending June 27). Two period ends less than
 * about half a quarter apart cannot both be one company's consecutive quarters.
 * Such rows are placed on a time axis, so each company's quarters sit at their
 * own dates and its line joins them.
 */
export function calendarsDiffer(rows: LineRow[]): boolean {
  const times = rows.map((row) => row.time);
  if (times.some((time) => time === null)) return false;
  const sorted = (times as number[]).slice().sort((a, b) => a - b);
  return sorted.some((time, index) => index > 0 && time - sorted[index - 1] < 45 * DAY);
}

/**
 * Calendar quarter ends (Mar 31, Jun 30, Sep 30, Dec 31) within the rows' dates,
 * for a time axis. At most ``max`` ticks: every other quarter when there are more.
 */
export function quarterTicks(rows: LineRow[], max = 8): number[] {
  const times = rows.map((row) => row.time).filter((time): time is number => time !== null);
  if (times.length === 0) return [];
  const low = Math.min(...times);
  const high = Math.max(...times);
  const ticks: number[] = [];
  const start = new Date(low);
  let year = start.getUTCFullYear();
  let month = Math.floor(start.getUTCMonth() / 3) * 3; // quarter's first month
  for (;;) {
    // The day before the next quarter's first day is this quarter's end.
    const end = Date.UTC(year, month + 3, 1) - DAY;
    if (end > high) break;
    if (end >= low) ticks.push(end);
    month += 3;
    if (month >= 12) {
      month -= 12;
      year += 1;
    }
  }
  if (ticks.length <= max) return ticks;
  const step = Math.ceil(ticks.length / max);
  // Keep the newest quarter, where the story ends.
  return ticks.filter((_, index) => (ticks.length - 1 - index) % step === 0);
}

/**
 * Which side of its last point each series' end label goes: the side its own
 * last segment leaves open (above after a rise, below after a fall). When two
 * lines end close together on the axis (`domain`), the highest labels above and
 * the lowest below instead, so their labels never sit between the lines.
 */
export function endLabelSides(
  rows: LineRow[],
  series: LineSeries[],
  [low, high]: [number, number],
): Record<string, "above" | "below"> {
  const sides: Record<string, "above" | "below"> = {};
  const ends: { key: string; value: number }[] = [];
  for (const { key } of series) {
    const values = rows.map((row) => row[key]).filter((value): value is number => typeof value === "number");
    const [previous, last] = values.slice(-2);
    sides[key] = values.length > 1 && last < previous ? "below" : "above";
    if (values.length > 0) ends.push({ key, value: values[values.length - 1] });
  }
  ends.sort((a, b) => a.value - b.value);
  const span = high - low || 1;
  const close = ends.some((end, index) => index > 0 && (end.value - ends[index - 1].value) / span < CLOSE_ENDS);
  if (ends.length > 1 && close) {
    sides[ends[0].key] = "below";
    sides[ends[ends.length - 1].key] = "above";
  }
  return sides;
}

/** Ends nearer than this share of the axis would put two labels in each other's way. */
const CLOSE_ENDS = 0.3;

export interface BarRow {
  /** The company key the answer table's row shares. */
  key: string;
  name: string;
  value: number;
  amount: string;
  /** The amount, or the reason a value is missing. */
  label: string;
  missing: boolean;
  period: string;
  /** Index into the answer's evidence. */
  evidence: number | null;
  derived: boolean;
}

/** A bar without a finite value keeps its row, drawn as missing with "—". */
export function barRows(spec: BarChartSpec): BarRow[] {
  return spec.records.map((record) => {
    const missing = record.Missing || typeof record.Value !== "number" || !Number.isFinite(record.Value);
    return {
      key: record.Key ?? record.Company,
      name: record.Company,
      value: missing ? 0 : record.Value,
      amount: record.Amount,
      label: record.Missing ? record.Label : missing ? "—" : record.Label,
      missing,
      period: record.Period ?? "",
      evidence: typeof record.Evidence === "number" ? record.Evidence : null,
      derived: record.Derived === true,
    };
  });
}

/** More periods than this and a narrow axis shows every other label (newest kept). */
export const DENSE_PERIODS = 5;

/** A period label as its day over its year ("Mar 31, 2026"); one with no year ("FY2025") is one line. */
export function splitPeriod(period: string): [string, string] {
  const split = period.lastIndexOf(", ");
  return split > 0 ? [period.slice(0, split), period.slice(split + 2)] : [period, ""];
}

/** The longer line of a two-line period tick ("Mar 31" of "Mar 31, 2026"), to measure its width. */
export function tickLine(period: string): string {
  return splitPeriod(period)[0];
}

/**
 * Bars in the order of ``keys`` (the answer table's sorted rows); bars the
 * table does not name keep their place after them. No keys: the server's order.
 */
export function orderedBars(rows: BarRow[], keys: string[] | null): BarRow[] {
  if (!keys) return rows;
  const position = new Map<string, number>();
  keys.forEach((key, index) => {
    if (!position.has(key)) position.set(key, index);
  });
  const place = (row: BarRow) => position.get(row.key) ?? keys.length;
  return [...rows].sort((a, b) => place(a) - place(b));
}

/**
 * The value axis range. Bars grow from zero; a line pads its own range so a
 * trend is visible, without dipping below zero for positive data.
 */
export function valueDomain(
  values: (number | null | undefined)[],
  { zero }: { zero: boolean },
): [number, number] {
  const finite = values.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (finite.length === 0) return [0, 1];
  const low = Math.min(...finite);
  const high = Math.max(...finite);
  if (zero) {
    const domain: [number, number] = [Math.min(0, low), Math.max(0, high)];
    return domain[0] === domain[1] ? [0, 1] : domain;
  }
  const span = high - low || Math.abs(high) || 1;
  const pad = span * 0.08;
  const padded = low - pad;
  return [low >= 0 && padded < 0 ? 0 : padded, high + pad];
}

/**
 * A bar axis that ends at the first nice tick beyond the longest bar ($20B for
 * $18.2B, not $25B); the plot's margin, not the axis, holds the value labels.
 */
export function barTicks(values: (number | null | undefined)[]): number[] {
  return niceTicks(valueDomain(values, { zero: true }));
}

/** Clean axis ticks (steps of 1, 2 or 5 × 10ⁿ) covering the domain. */
export function niceTicks([low, high]: [number, number], count = 5): number[] {
  if (!(high > low)) {
    const [floor, ceiling] = [Math.min(0, low), Math.max(0, high)];
    return ceiling > floor ? niceTicks([floor, ceiling], count) : [0, 1];
  }
  const raw = (high - low) / (count - 1);
  const power = 10 ** Math.floor(Math.log10(raw));
  const error = raw / power;
  const step = power * (error >= Math.sqrt(50) ? 10 : error >= Math.sqrt(10) ? 5 : error >= Math.SQRT2 ? 2 : 1);
  const first = Math.floor(low / step);
  const last = Math.ceil(high / step);
  const ticks: number[] = [];
  for (let i = first; i <= last; i += 1) ticks.push(Number((i * step).toPrecision(12)) || 0);
  return ticks;
}
