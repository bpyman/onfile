import { expect, test } from "@playwright/test";
import { Analyst } from "./analyst";

// Each test gets a fresh browser context, so a fresh thread (ADR 0006 cutover criteria).

// The hosted demo lands on the live runtime with the recorded one a click away; the
// local run starts the API on the recorded runtime with PUBLIC_DEMO off. Neither is locked.
const deployed = Boolean(process.env.PLAYWRIGHT_BASE_URL);

test.describe("guided stories", () => {
  test("Verify a quarterly fact shows the fact card and its evidence", async ({ page }) => {
    const analyst = new Analyst(page);
    await analyst.open();
    await analyst.tell("Verify a quarterly fact");

    const card = analyst.factCards(/, Microsoft Corporation$/);
    await expect(card).toBeVisible();
    await expect(card).toContainText("$");
    // Microsoft's latest quarter is its fiscal Q4, derived from the 10-K (ADR 0007).
    await expect(card).toContainText(/10-[KQ]/);
    await expect(card.getByRole("link", { name: /filing/i })).toBeVisible();
    await expect(page.getByRole("region", { name: "Evidence inspector" })).toBeVisible();
  });

  test("Compare four quarters draws a trend and its table", async ({ page }) => {
    const analyst = new Analyst(page);
    await analyst.open();
    await analyst.tell("Compare four quarters");

    await expect(analyst.charts()).toHaveCount(1);
    await expect(analyst.charts()).toContainText("Revenue");
    await expect(analyst.tables()).toBeVisible();
    await expect(analyst.tables().getByRole("row")).toHaveCount(5);
  });

  test("Rank then inspect filings ranks ten companies and links each filing", async ({ page }) => {
    const analyst = new Analyst(page);
    await analyst.open();
    await analyst.tell("Rank then inspect filings");

    await expect(analyst.charts()).toHaveCount(1);
    const table = analyst.tables();
    await expect(table.getByRole("row")).toHaveCount(11);
    await expect(table.getByRole("link", { name: /filing/i })).toHaveCount(10);

    await table.getByRole("radio", { name: "Full" }).click();
    await expect(table.getByRole("columnheader", { name: /accession/i })).toBeVisible();
  });

  test("What changed in the 10-Q shows each changed section", async ({ page }) => {
    const analyst = new Analyst(page);
    await analyst.open();
    await analyst.tell("What changed in the 10-Q");

    const changes = page.getByRole("region", { name: "Filing changes" });
    const kind = "(added|removed|changed)$";
    // Changes that move a figure come first; the rest open with "Show more" and the wording row.
    await changes.getByRole("button", { name: /^Show \d+ more changes?$/ }).click();
    await changes.getByText(/^\d+ wording-only edits?/).click();
    // Recorded 10-Qs a year apart: each reviewed section has at least one change.
    for (const section of ["Management's Discussion and Analysis", "Risk Factors"]) {
      const name = new RegExp(`^${section}, ${kind}`);
      await expect(changes.getByRole("article", { name }).first()).toBeVisible();
    }
    await expect(changes.getByRole("link", { name: "Open previous filing" }).first()).toBeVisible();
  });
});

test("compare four quarters, then add Apple", async ({ page }) => {
  const analyst = new Analyst(page);
  await analyst.open();
  await analyst.tell("Compare four quarters");
  await analyst.ask("add Apple");

  await expect(analyst.charts()).toHaveCount(2);
  const legend = analyst.charts().last().getByRole("list", { name: "Series" });
  await expect(legend.getByRole("listitem")).toHaveText([/Microsoft Corporation/, /Apple Inc\./]);
  await expect(analyst.activeAnalysis()).toContainText("AAPL");
  await expect(analyst.counter()).toHaveAttribute("data-turns", "2");
});

test("a clarify button answers the question and closes it", async ({ page }) => {
  const analyst = new Analyst(page);
  await analyst.open();
  await analyst.ask("What was Google's latest quarterly profit?");

  const clarify = analyst.clarify();
  await expect(clarify).toBeVisible();
  const candidates = clarify.getByRole("button");
  await expect(candidates).toHaveText([/Gross profit/, /Operating income/, /Net income/]);
  await expect(candidates.first()).toBeEnabled();

  await analyst.choose(/Net income/);

  await expect(analyst.factCards(/^Net income, /)).toBeVisible();
  await expect(clarify.getByRole("button", { name: /Net income/ })).toBeDisabled();
  await expect(clarify).toContainText("Answered below.");
  // The answer bubble shows the chosen label, not the slug it sent; the label already
  // says what was sent, so there is no "Sent as" note on it.
  const reply = analyst.conversation().getByRole("listitem").nth(1).locator("p").first();
  await expect(reply).toHaveText("Net income");
  await expect(page.getByTitle(/^Sent as/)).toHaveCount(0);
});

test("a reload resumes the thread and Start over clears it", async ({ page }) => {
  const analyst = new Analyst(page);
  await analyst.open();
  await analyst.tell("Verify a quarterly fact");

  await page.reload();
  await expect(analyst.factCards(/, Microsoft Corporation$/)).toBeVisible();
  await expect(analyst.counter()).toHaveAttribute("data-turns", "1");

  await analyst.startOver();
  await expect(analyst.counter()).toBeHidden();

  await page.reload();
  await expect(analyst.story("Verify a quarterly fact")).toBeEnabled();
  await expect(analyst.conversation()).toBeHidden();
});

test("Start over asks first, and keeps the conversation when declined", async ({ page }) => {
  const analyst = new Analyst(page);
  await analyst.open();
  await analyst.tell("Verify a quarterly fact");

  await page.getByRole("button", { name: "Start over" }).click();
  const confirm = page.getByRole("alertdialog", { name: "Start over?" });
  await expect(confirm).toContainText("This clears the current conversation.");
  await confirm.getByRole("button", { name: "Cancel" }).click();

  await expect(confirm).toBeHidden();
  await expect(analyst.counter()).toHaveAttribute("data-turns", "1");
  await expect(analyst.factCards(/, Microsoft Corporation$/)).toBeVisible();
});

test("Start over works where the browser's own dialogs never show", async ({ page }) => {
  // In-app browsers (LinkedIn, Slack) answer window.confirm with Cancel, unseen.
  await page.addInitScript(() => {
    window.confirm = () => false;
  });
  const dialogs: string[] = [];
  page.on("dialog", (dialog) => {
    dialogs.push(dialog.message());
    void dialog.dismiss();
  });
  const analyst = new Analyst(page);
  await analyst.open();
  await analyst.tell("Verify a quarterly fact");

  await analyst.startOver();
  await expect(analyst.counter()).toBeHidden();
  expect(dialogs).toEqual([]);
});

test("Start over drops an answer that is still running", async ({ page }) => {
  const analyst = new Analyst(page);
  await analyst.open();
  let releaseTurn = () => {};
  const turnHeld = new Promise<void>((resolve) => (releaseTurn = resolve));
  await page.route(/\/api\/threads\/[0-9a-f-]+\/turns$/, async (route) => {
    await turnHeld;
    await route.continue().catch(() => undefined);
  });
  const composer = page.getByRole("textbox", { name: "Ask a question" });
  await composer.fill("What was Apple's latest quarterly revenue?");
  await composer.press("Enter");
  await expect(page.locator('[data-turn="pending"]')).toBeVisible();

  await analyst.startOver();
  await expect(page.locator('[data-turn="pending"]')).toBeHidden();
  await expect(analyst.counter()).toBeHidden();

  // The dropped answer finishing later does not come back into the new conversation.
  releaseTurn();
  await page.waitForTimeout(1500);
  await expect(analyst.conversation()).toBeHidden();
  await page.getByRole("textbox", { name: "Ask a question" }).fill("Microsoft revenue");
  await expect(page.getByRole("button", { name: "Send" })).toBeEnabled();
});

test("a second tab follows the first when it starts over", async ({ page, context }) => {
  const first = new Analyst(page);
  await first.open();
  await first.tell("Verify a quarterly fact");
  const other = await context.newPage();
  const second = new Analyst(other);
  // The second tab resumes the same thread rather than landing.
  await other.goto("/");
  await expect(second.factCards(/, Microsoft Corporation$/)).toBeVisible();

  await first.startOver();

  await expect(other.getByText("This conversation changed in another tab")).toBeVisible();
  await expect(second.conversation()).toBeHidden();
});

test("a reload keeps the window from starting another thread until the saved one is back", async ({ page }) => {
  const analyst = new Analyst(page);
  await analyst.open();
  await analyst.tell("Verify a quarterly fact");
  const savedId = await page.evaluate(() => localStorage.getItem("financial-analyst-agent.thread-id"));
  expect(savedId).toBeTruthy();

  let releaseThread = () => {};
  const threadHeld = new Promise<void>((resolve) => (releaseThread = resolve));
  await page.route(/\/api\/threads\/[0-9a-f-]+$/, async (route) => {
    if (route.request().method() === "GET") await threadHeld;
    await route.continue();
  });
  const created: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && new URL(request.url()).pathname === "/api/threads") {
      created.push(request.url());
    }
  });
  await page.reload();

  const loading = page.getByRole("button", { name: "Loading your thread" });
  await expect(loading).toBeDisabled();
  const composer = page.getByRole("textbox", { name: "Ask a question" });
  await composer.fill("What was Apple's latest quarterly revenue?");
  await composer.press("Enter");
  await expect(loading).toBeDisabled();

  releaseThread();
  await expect(analyst.factCards(/, Microsoft Corporation$/)).toBeVisible();
  await expect(analyst.counter()).toHaveAttribute("data-turns", "1");
  await expect(page.getByRole("button", { name: "Send" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Start over" })).toBeEnabled();
  expect(created).toEqual([]);
  expect(await page.evaluate(() => localStorage.getItem("financial-analyst-agent.thread-id"))).toBe(savedId);
});

test("Start over works while a saved thread is slow to come back", async ({ page }) => {
  const analyst = new Analyst(page);
  await analyst.open();
  await analyst.tell("Verify a quarterly fact");
  const savedId = await page.evaluate(() => localStorage.getItem("financial-analyst-agent.thread-id"));

  let releaseThread = () => {};
  const threadHeld = new Promise<void>((resolve) => (releaseThread = resolve));
  await page.route(/\/api\/threads\/[0-9a-f-]+$/, async (route) => {
    if (route.request().method() === "GET" && route.request().url().endsWith(savedId ?? "")) await threadHeld;
    await route.continue();
  });
  await page.reload();
  await expect(page.getByRole("button", { name: "Loading your thread" })).toBeDisabled();

  await analyst.startOver();
  await expect(analyst.counter()).toBeHidden();
  const freshId = await page.evaluate(() => localStorage.getItem("financial-analyst-agent.thread-id"));
  expect(freshId).not.toBe(savedId);

  // The saved thread arriving late does not replace the fresh one.
  releaseThread();
  await page.waitForTimeout(1500);
  await expect(analyst.conversation()).toBeHidden();
  await page.getByRole("textbox", { name: "Ask a question" }).fill("Microsoft revenue");
  await expect(page.getByRole("button", { name: "Send" })).toBeEnabled();
});

test("the storefront reports the deployment's runtime and asks for that runtime's snapshot", async ({ page }) => {
  const asked = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/meta");
  await new Analyst(page).open();
  const response = await asked;

  // Until the deployment says which runtime it runs, the window names none.
  expect(new URL(response.url()).searchParams.get("runtime")).toBeNull();
  expect((await response.json()).runtime).toEqual({ default: deployed ? "live" : "recorded", locked: false });
});

test("the composer takes its message limit from the server", async ({ page }) => {
  await page.route("**/api/meta**", async (route) => {
    const response = await route.fetch();
    await route.fulfill({ response, json: { ...(await response.json()), max_message_chars: 50 } });
  });
  await new Analyst(page).open();

  await expect(page.getByRole("textbox", { name: "Ask a question" })).toHaveAttribute("maxlength", "50");
  // The storefront asks again once it knows the runtime; that read may still be in the route.
  await page.unrouteAll({ behavior: "ignoreErrors" });
});

test("a question sent before the storefront loads leaves the runtime to the deployment", async ({ page }) => {
  let releaseMeta = () => {};
  const metaHeld = new Promise<void>((resolve) => (releaseMeta = resolve));
  await page.route("**/api/meta**", async (route) => {
    await metaHeld;
    await route.continue();
  });
  const analyst = new Analyst(page);
  await page.goto("/");

  const created = page.waitForRequest(
    (request) => request.method() === "POST" && new URL(request.url()).pathname === "/api/threads",
  );
  await page.getByRole("textbox", { name: "Ask a question" }).fill("What was Microsoft's latest quarterly pretax income?");
  await page.keyboard.press("Enter");
  expect((await created).postDataJSON()).toEqual({});

  releaseMeta();
  await analyst.waitForTurn(1);
});

test("a reload while a turn runs picks the answer up when it lands", async ({ page }) => {
  const analyst = new Analyst(page);
  await analyst.open();
  await analyst.tell("Verify a quarterly fact");

  // The server reports the turn still in flight for the first two reads after the reload.
  let inFlightReads = 2;
  await page.route(/\/api\/threads\/[0-9a-f-]+$/, async (route) => {
    if (route.request().method() !== "GET" || inFlightReads === 0) return route.continue();
    inFlightReads -= 1;
    const response = await route.fetch();
    const view = await response.json();
    await route.fulfill({ response, json: { ...view, turns: [], turn_in_flight: true } });
  });
  await page.reload();

  await expect(page.getByText("Finishing your last question…")).toBeVisible();
  await expect(page.getByRole("button", { name: "Analysis running" })).toBeDisabled();
  await expect(analyst.factCards(/, Microsoft Corporation$/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Send" })).toBeVisible();
  await expect(analyst.counter()).toHaveAttribute("data-turns", "1");
});

test("the window installs as an app with the project's icons", async ({ page, request }) => {
  await page.goto("/");
  const href = await page.locator('link[rel="manifest"]').getAttribute("href");
  expect(href).toBeTruthy();

  const manifest = await (await request.get(href!)).json();
  expect(manifest).toMatchObject({ name: "Onfile", display: "standalone", start_url: "/" });
  const sizes = manifest.icons.map((icon: { sizes: string }) => icon.sizes);
  expect(sizes).toEqual(expect.arrayContaining(["192x192", "512x512"]));
  for (const icon of manifest.icons) {
    const response = await request.get(icon.src);
    expect(response.ok(), icon.src).toBe(true);
    expect(response.headers()["content-type"]).toBe("image/png");
  }
});

test("the site answers favicon.ico and robots.txt", async ({ request }) => {
  const favicon = await request.get("/favicon.ico");
  expect(favicon.ok()).toBe(true);
  expect(favicon.headers()["content-type"]).toContain("image/");
  const robots = await request.get("/robots.txt");
  expect(await robots.text()).toContain("Disallow: /api/");
});

test("a company on its own gets an overview, and a suggestion extends it", async ({ page }) => {
  const analyst = new Analyst(page);
  await analyst.open();
  await analyst.ask("How is Nvidia doing?");

  const table = analyst.tables();
  await expect(table.getByRole("columnheader", { name: "Net margin" })).toBeVisible();
  await expect(table.getByRole("row")).toHaveCount(2);
  // Small trends of the last few quarters, one chart per measure.
  const trends = page.getByRole("region", { name: "Recent quarters" });
  await expect(trends.getByRole("figure")).toHaveCount(2);
  await expect(trends.getByRole("figure", { name: /Net margin/ })).toBeVisible();

  const next = page.getByRole("navigation", { name: "Suggested next questions" });
  await next.getByRole("button", { name: "show year-over-year" }).click();
  await analyst.waitForTurn(2);
  // One row per quarter, with each metric's year-over-year change in its own column.
  await expect(analyst.tables().last().getByRole("columnheader", { name: "Revenue, YoY" })).toBeVisible();
  // Only the latest answer offers next questions.
  await expect(next).toHaveCount(1);
});

test("sorting the table re-orders the chart's bars with it", async ({ page }) => {
  const analyst = new Analyst(page);
  await analyst.open();
  await analyst.ask("Compare Eli Lilly and Merck net margins");
  const table = page.getByRole("region", { name: "Answer table" });
  const header = table.getByRole("columnheader", { name: /Net margin/ });

  await header.getByRole("button").click();

  await expect(header).toHaveAttribute("aria-sort", "descending");
  await expect(page.getByText("Ordered as the table: Net margin, largest first.")).toBeVisible();
  const margins = await table.locator("tbody tr td:nth-child(2)").allInnerTexts();
  const values = margins.map((text) => Number.parseFloat(text));
  expect(values).toEqual([...values].sort((a, b) => b - a));

  await table.getByRole("button", { name: "Original order" }).click();
  await expect(header).toHaveAttribute("aria-sort", "none");
});

test("an answer saves as Markdown with the table and its filings", async ({ page }) => {
  const analyst = new Analyst(page);
  await analyst.open();
  await analyst.ask("Compare Eli Lilly and Merck net margins");

  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Save answer as Markdown" }).click(),
  ]);

  expect(download.suggestedFilename()).toBe("compare-eli-lilly-and-merck-net-margins.md");
  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream) chunks.push(chunk as Buffer);
  const text = Buffer.concat(chunks).toString("utf8");
  expect(text).toContain("## Compare Eli Lilly and Merck net margins");
  expect(text).toMatch(/\| Eli Lilly and Company \|/);
  expect(text).toMatch(/\*\*SEC filings\*\*\n\n- \[Eli Lilly and Company, 10-Q [\d-]+\]\(https:\/\/www\.sec\.gov\//);
});

test("the status line explains how the runtimes differ", async ({ page }) => {
  const analyst = new Analyst(page);
  await analyst.open();
  await page.getByRole("button", { name: "How runtimes differ" }).click();

  const guide = page.getByRole("dialog", { name: "How runtimes differ" });
  await expect(guide).toBeVisible();
  await expect(guide.getByRole("heading", { name: /Recorded/ })).toBeVisible();
  await expect(guide.getByRole("heading", { name: /Live/ })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(guide).toBeHidden();
});

test("a re-sorted ranking stops calling its bars ordered by market cap", async ({ page }) => {
  const analyst = new Analyst(page);
  await analyst.open();
  await analyst.tell("Rank then inspect filings");
  const chart = analyst.charts().last();
  await expect(chart).toContainText("Ordered by market cap");

  await analyst.tables().last().getByRole("columnheader", { name: /Research and development/ }).getByRole("button").click();

  await expect(chart).toContainText("Ordered as the table: Research and development, largest first.");
  await expect(chart).not.toContainText("Ordered by market cap");
});
