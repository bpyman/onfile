import type { DisplayTable } from "./types";

/**
 * Sorting an answer table by a column. Amounts, ranks and dates sort on the
 * server's numbers for each cell (ADR 0006: the browser formats nothing, and
 * "$109.42 B" does not sort as text); other columns sort on their text.
 */
export type SortDirection = "ascending" | "descending";

export interface TableSort {
  key: string;
  direction: SortDirection;
}

function columnIndex(table: DisplayTable, key: string): number {
  return table.keys.indexOf(key);
}

/** Whether a column sorts on numbers: some row has a number for it. */
export function sortsNumerically(table: DisplayTable, key: string): boolean {
  const index = columnIndex(table, key);
  return index >= 0 && table.numbers.some((row) => typeof row[index] === "number");
}

/**
 * The next sort after clicking a column: numbers start largest first and text
 * A to Z; a second click reverses it; a third returns the server's order.
 */
export function nextSort(table: DisplayTable, current: TableSort | null, key: string): TableSort | null {
  const first: SortDirection = sortsNumerically(table, key) ? "descending" : "ascending";
  if (!current || current.key !== key) return { key, direction: first };
  if (current.direction === first) {
    return { key, direction: first === "descending" ? "ascending" : "descending" };
  }
  return null;
}

/**
 * Row indices in display order. Stable, and a row with no value for the column
 * (a missing fact) stays last whichever way the column is sorted.
 */
export function sortedRowIndices(table: DisplayTable, sort: TableSort | null): number[] {
  const order = table.rows.map((_, index) => index);
  if (!sort) return order;
  const index = columnIndex(table, sort.key);
  if (index < 0) return order;
  const sign = sort.direction === "ascending" ? 1 : -1;
  if (sortsNumerically(table, sort.key)) {
    const value = (row: number) => table.numbers[row]?.[index];
    return order.sort((a, b) => {
      const left = value(a);
      const right = value(b);
      if (typeof left !== "number" || typeof right !== "number") {
        return (typeof left === "number" ? 0 : 1) - (typeof right === "number" ? 0 : 1);
      }
      return (left - right) * sign;
    });
  }
  const text = (row: number) => (table.rows[row]?.[index] ?? "").trim();
  return order.sort((a, b) => {
    const left = text(a);
    const right = text(b);
    if (!left || !right) return (left ? 0 : 1) - (right ? 0 : 1);
    return left.localeCompare(right, undefined, { numeric: true, sensitivity: "base" }) * sign;
  });
}

/** "Revenue, largest first": what the table is sorted by, for the chart to say. */
export function sortDescription(table: DisplayTable, sort: TableSort): string {
  const header = table.headers[columnIndex(table, sort.key)] ?? sort.key;
  const numeric = sortsNumerically(table, sort.key);
  const dated = sort.key.endsWith("_date");
  const [down, up] = dated
    ? ["newest first", "oldest first"]
    : numeric
      ? ["largest first", "smallest first"]
      : ["Z to A", "A to Z"];
  const way = sort.direction === "descending" ? down : up;
  return `${header}, ${way}`;
}
