import { devices, expect, test, type Download } from "@playwright/test";
import { Analyst } from "./analyst";

// The window's batch-five features on the recorded API: figures that open
// their source, question-only share links, CSV, editable chips, the instant
// story on a cold start, keyboard shortcuts, and the phone layout.

const TURNS = /\/api\/threads\/[0-9a-f-]+\/turns$/;

async function text(download: Download): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of await download.createReadStream()) chunks.push(chunk as Buffer);
  return Buffer.concat(chunks).toString("utf8");
}

test("a table cell or a bar opens its source in the inspector", async ({ page }) => {
  const analyst = new Analyst(page);
  await analyst.open();
  await analyst.tell("Compare four quarters");

  const inspector = page.getByRole("region", { name: "Evidence inspector" });
  const choice = inspector.getByLabel("Evidence item");
  await analyst.tables().getByRole("button", { name: "$82.89 B" }).click();
  await expect(choice.locator("option:checked")).toHaveText(/Revenue · Jan 1, 2026 – Mar 31, 2026$/);
  await expect(inspector).toBeInViewport();
  // Enter on a focused cell does the same.
  await analyst.tables().getByRole("button", { name: "$77.67 B" }).focus();
  await page.keyboard.press("Enter");
  await expect(choice.locator("option:checked")).toHaveText(/Revenue · Jul 1, 2025 – Sep 30, 2025$/);

  await analyst.ask("What are the top 10 tech companies and R&D spend for each?");
  const ranked = page.getByRole("region", { name: "Evidence inspector (answer 2)" });
  // The second bar is Apple's.
  await page.getByRole("figure").last().locator(".recharts-bar-rectangle").nth(1).click();
  await expect(ranked.getByLabel("Evidence item").locator("option:checked")).toHaveText(/Apple Inc\. · Research and development/);
  // The options follow the table: the ranking's first row leads.
  await expect(ranked.getByLabel("Evidence item").locator("option").first()).toHaveText(/^1\. NVIDIA Corporation/);
});

test("several companies' quarters read across, and Copy, Save and CSV keep that layout", async ({ page }) => {
  const analyst = new Analyst(page);
  await analyst.open();
  await analyst.tell("Compare four quarters");
  await analyst.ask("add Apple");

  // The legend hides and shows a company's line.
  const legend = analyst.charts().last().getByRole("list", { name: "Series" });
  const apple = legend.getByRole("button", { name: "Apple Inc." });
  await apple.click();
  await expect(apple).toHaveAttribute("aria-pressed", "false");
  await apple.press("Enter");
  await expect(apple).toHaveAttribute("aria-pressed", "true");

  const table = analyst.tables().last();
  await expect(table.getByRole("columnheader")).toHaveText([/Quarter ended/, /MSFT/, /AAPL/]);
  await expect(table.getByRole("row")).toHaveCount(5);
  await table.getByRole("columnheader", { name: /Quarter ended/ }).getByRole("button").click();
  await table.getByRole("columnheader", { name: /Quarter ended/ }).getByRole("button").click();

  const [csv] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Save table as CSV" }).last().click(),
  ]);
  expect(csv.suggestedFilename()).toBe("add-apple.csv");
  const lines = (await text(csv)).trim().split("\r\n");
  expect(lines[0]).toBe("Quarter ended,MSFT,AAPL");
  // Sorted oldest first, with each amount unrounded.
  expect(lines[1]).toBe("2025-09-30,77673000000,102466000000");
  expect(lines).toHaveLength(5);

  const [markdown] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Save answer as Markdown" }).last().click(),
  ]);
  expect(await text(markdown)).toContain("| Quarter ended | MSFT | AAPL |");
});

test("a shared link asks its question once, in a new conversation, and leaves the address clean", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  const analyst = new Analyst(page);
  await analyst.open();
  await analyst.tell("Verify a quarterly fact");
  await page.getByRole("button", { name: "Copy link" }).click();
  const link = await page.evaluate(() => navigator.clipboard.readText());
  expect(new URL(link).searchParams.get("q")).toBe("What was Microsoft's latest quarterly pretax income?");
  expect(new URL(link).searchParams.get("rt")).toBe("recorded");

  await page.goto("/?q=How%20is%20Nvidia%20doing%3F&rt=recorded");
  await analyst.waitForTurn(1);
  await expect(page.getByText("How is Nvidia doing?").first()).toBeVisible();
  // The earlier conversation is not this one.
  await expect(page.getByText("What was Microsoft's latest quarterly pretax income?")).toHaveCount(0);
  expect(new URL(page.url()).search).toBe("");
  await page.reload();
  await analyst.waitForTurn(1);
  await expect(analyst.conversation().locator(":scope > li")).toHaveCount(1);
});

test("a chip's × removes it and + adds to the analysis", async ({ page }) => {
  const analyst = new Analyst(page);
  await analyst.open();
  await analyst.tell("Compare four quarters");
  await analyst.ask("add Apple");
  await expect(analyst.activeAnalysis()).toContainText("AAPL");

  await page.getByRole("button", { name: "Remove AAPL" }).click();
  await analyst.waitForTurn(3);
  await expect(analyst.activeAnalysis()).not.toContainText("AAPL");
  await expect(page.getByText("remove Apple")).toBeVisible();

  await page.getByRole("button", { name: "Add to the analysis" }).click();
  await page.getByRole("menu", { name: "Add to the analysis" }).getByRole("menuitem", { name: /^Net income/ }).click();
  await analyst.waitForTurn(4);
  await expect(analyst.activeAnalysis()).toContainText("Net income");
});

test("while the service wakes, a story shows its recorded answer at once, then the fresh one", async ({ page }) => {
  // Nothing that would show the API awake answers; the turn itself is slow.
  await page.route("**/api/health", () => undefined);
  await page.route("**/api/meta**", () => undefined);
  let release: () => void = () => undefined;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(TURNS, async (route) => {
    await held;
    await route.continue();
  });
  const analyst = new Analyst(page);
  await page.goto("/");
  await analyst.story("Verify a quarterly fact").click();

  const pending = page.locator('[data-turn="pending"]');
  await expect(pending.getByText("Demo data")).toBeVisible({ timeout: 5_000 });
  await expect(pending.getByRole("region", { name: /Pretax income, Microsoft Corporation/ })).toBeVisible();
  release();
  await analyst.waitForTurn(1);
  await expect(page.getByText("Demo data")).toHaveCount(0);
  await expect(page.getByText("Quarterly lookup")).toBeVisible();
});

test("/ jumps to the question box and ↑ brings back the last question", async ({ page }) => {
  const analyst = new Analyst(page);
  await analyst.open();
  const box = page.getByRole("textbox", { name: "Ask a question" });
  await page.locator("body").click({ position: { x: 5, y: 300 } });
  await page.keyboard.press("/");
  await expect(box).toBeFocused();
  await expect(box).toHaveValue("");

  await analyst.tell("Verify a quarterly fact");
  await box.focus();
  await page.keyboard.press("ArrowUp");
  await expect(box).toHaveValue("What was Microsoft's latest quarterly pretax income?");
  // Typing / in the box writes it.
  await box.fill("");
  await page.keyboard.type("R/D");
  await expect(box).toHaveValue("R/D");
});

test("a why question shows management's explanation from the 10-Q, quoted and linked", async ({ page }) => {
  const analyst = new Analyst(page);
  await analyst.open();
  await analyst.ask("What caused Alphabet's cost of revenue to rise year over year last quarter?");
  const panel = page.getByRole("region", { name: "Management's explanation" });
  await expect(panel.getByText("From Alphabet's 10-Q for the quarter ended Jun 30, 2026")).toBeVisible();
  await expect(panel.getByText("Written by the model from the quoted paragraphs")).toBeVisible();
  await expect(panel.locator("blockquote")).toHaveCount(3);
  await expect(panel.getByRole("link", { name: "Read in the filing" }).first()).toHaveAttribute("href", /goog-20260630\.htm#:~:text=/);
  // The panel replaces the note that filings report what changed, not why.
  await expect(page.getByText(/Filings report what/)).toHaveCount(0);
});

// The suite runs in Chromium; the phone is its size, touch and user agent, not WebKit.
const { viewport, userAgent, deviceScaleFactor, isMobile, hasTouch } = devices["iPhone 13"];
const iPhone = { viewport, userAgent, deviceScaleFactor, isMobile, hasTouch };

test.describe("on a phone", () => {
  test.use(iPhone);

  test("the first screen shows a story, and the header keeps its tools in a menu", async ({ page }) => {
    const analyst = new Analyst(page);
    await analyst.open();
    await expect(analyst.story("Verify a quarterly fact")).toBeInViewport();
    await expect(page.getByRole("button", { name: "Start over" })).toBeHidden();
    await page.getByRole("button", { name: "Menu" }).click();
    await expect(page.getByRole("menuitem", { name: "Start over" })).toBeVisible();
    await page.keyboard.press("Escape");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });

  test("an overview reads as a grid and a figure opens its source in a sheet", async ({ page }) => {
    const analyst = new Analyst(page);
    await analyst.open();
    await analyst.ask("How is Nvidia doing?");
    const table = analyst.tables();
    await expect(table.getByRole("term")).toHaveText(["Revenue", "Net income", "Gross margin", "Operating margin", "Net margin"]);
    // Sources stay folded until asked for.
    await expect(page.getByRole("region", { name: "Evidence inspector" })).toBeHidden();
    await table.getByRole("definition").first().getByRole("button").click();
    const sheet = page.getByRole("dialog", { name: /NVIDIA Corporation · Revenue/ });
    await expect(sheet).toBeVisible();
    await expect(sheet.getByText("96,221,000,000")).toBeVisible();
    await sheet.getByRole("button", { name: "Close source" }).click();
    await expect(sheet).toBeHidden();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });

  test("management's explanation shows its paragraphs when asked", async ({ page }) => {
    const analyst = new Analyst(page);
    await analyst.open();
    await analyst.ask("Nvidia operating income");
    await analyst.ask("why?");
    const panel = page.getByRole("region", { name: /^Management's explanation/ });
    await expect(panel.getByText("Written by the model from the quoted paragraphs")).toBeVisible();
    await expect(panel.locator("blockquote").first()).toBeHidden();
    await panel.getByRole("button", { name: "Show the paragraphs" }).click();
    await expect(panel.locator("blockquote").first()).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
