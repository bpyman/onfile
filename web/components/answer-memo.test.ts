import { describe, expect, it } from "vitest";
import { Answer } from "./answer";

describe("Answer", () => {
  it("is memoised", () => {
    expect(Answer).toHaveProperty("compare", null);
  });
});
