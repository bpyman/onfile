import { describe, expect, it } from "vitest";
import { nextSort, sortDescription, sortedRowIndices } from "./table-sort";
import type { DisplayTable } from "./types";

const table: DisplayTable = {
  headers: ["Company", "Revenue", "Quarter ended"],
  keys: ["company_name", "value", "end_date"],
  rows: [
    ["Microsoft", "$90.01 B", "Jun 30, 2026"],
    ["Apple", "$109.42 B", "Jun 27, 2026"],
    ["Nvidia", "Missing fact", "Jul 26, 2026"],
    ["Alphabet", "$119.80 B", "Jun 30, 2026"],
  ],
  numbers: [
    [null, 90.01e9, 739797],
    [null, 109.42e9, 739794],
    [null, null, 739823],
    [null, 119.8e9, 739797],
  ],
  row_keys: ["MSFT", "AAPL", "NVDA", "GOOG"],
};

describe("sortedRowIndices", () => {
  it("sorts amounts on the server's numbers, not their text, with missing values last", () => {
    expect(sortedRowIndices(table, { key: "value", direction: "descending" })).toEqual([3, 1, 0, 2]);
    expect(sortedRowIndices(table, { key: "value", direction: "ascending" })).toEqual([0, 1, 3, 2]);
  });

  it("sorts text A to Z and dates by day, keeping ties in the server's order", () => {
    expect(sortedRowIndices(table, { key: "company_name", direction: "ascending" })).toEqual([3, 1, 0, 2]);
    expect(sortedRowIndices(table, { key: "end_date", direction: "ascending" })).toEqual([1, 0, 3, 2]);
  });

  it("keeps the server's order when unsorted", () => {
    expect(sortedRowIndices(table, null)).toEqual([0, 1, 2, 3]);
  });
});

describe("nextSort", () => {
  it("starts numbers largest first and text A to Z, then reverses, then resets", () => {
    const first = nextSort(table, null, "value");
    expect(first).toEqual({ key: "value", direction: "descending" });
    const second = nextSort(table, first, "value");
    expect(second).toEqual({ key: "value", direction: "ascending" });
    expect(nextSort(table, second, "value")).toBeNull();
    expect(nextSort(table, second, "company_name")).toEqual({ key: "company_name", direction: "ascending" });
  });
});

describe("sortDescription", () => {
  it("names the column and the direction in words", () => {
    expect(sortDescription(table, { key: "value", direction: "descending" })).toBe("Revenue, largest first");
    expect(sortDescription(table, { key: "company_name", direction: "ascending" })).toBe("Company, A to Z");
  });
});
