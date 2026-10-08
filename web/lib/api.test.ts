import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  BAD_RESPONSE,
  createThread,
  getMeta,
  getThread,
  readMeta,
  readThreadView,
  readTurnEvent,
  runTurn,
} from "./api";

const META = {
  runtime: { default: "recorded", locked: false },
  runtime_copy: { recorded: "Recorded runtime — x", live: "Live runtime — y", locked: "off" },
  snapshot: { banner: "Universe as of May 1", stale: false },
  example_query: "Apple revenue",
  guided_stories: [{ label: "Verify a quarterly fact", question: "Microsoft pretax income?" }],
  capabilities: [{ description: "Look up", examples: ["Apple revenue"] }],
  metric_groups: [{ title: "Reported", names: ["Revenue"] }],
  max_message_chars: 2000,
};

describe("getMeta", () => {
  afterEach(() => vi.unstubAllGlobals());

  function stubFetch(body: unknown = META) {
    const fetch = vi.fn(async () => new Response(JSON.stringify(body), { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    return fetch;
  }

  it("names the runtime whose snapshot banner it wants", async () => {
    const fetch = stubFetch();
    await getMeta("live");
    expect(fetch).toHaveBeenCalledWith("/api/meta?runtime=live", expect.anything());
  });

  it("leaves the runtime to the deployment when none is named", async () => {
    const fetch = stubFetch();
    await getMeta();
    expect(fetch).toHaveBeenCalledWith("/api/meta", expect.anything());
  });

  it("reports a cut-off reply as unreadable, not as the service being unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response('{"runtime": {"def', { status: 200 })));
    await expect(getMeta()).rejects.toMatchObject({ message: BAD_RESPONSE, status: 502 });
  });
});

describe("readMeta", () => {
  it("keeps a well-formed storefront as sent", () => {
    expect(readMeta(META)).toMatchObject({ ...META, runtime_guide: undefined });
  });

  it("refuses a reply with no runtime, since nothing can be labelled without one", () => {
    expect(() => readMeta({})).toThrow(BAD_RESPONSE);
    expect(() => readMeta([])).toThrow(BAD_RESPONSE);
  });

  it("turns missing lists and nulls into empty ones", () => {
    const meta = readMeta({
      runtime: { default: "live" },
      runtime_copy: null,
      snapshot: null,
      guided_stories: null,
      capabilities: [{ description: "News", examples: null }, null, { examples: ["x"] }],
      metric_groups: "nope",
      max_message_chars: -5,
    });
    expect(meta).toMatchObject({
      runtime: { default: "live", locked: false },
      runtime_copy: { recorded: "", live: "", locked: "" },
      snapshot: null,
      guided_stories: [],
      capabilities: [{ description: "News", examples: [] }],
      metric_groups: [],
      max_message_chars: null,
    });
  });
});

describe("readThreadView", () => {
  it("refuses a thread with no id", () => {
    expect(() => readThreadView(null)).toThrow(BAD_RESPONSE);
    expect(() => readThreadView({})).toThrow(BAD_RESPONSE);
  });

  it("fills a stored turn's missing fields so rendering cannot trip on them", () => {
    const view = readThreadView({
      thread_id: "t",
      turns: [
        { index: 0, message: "q", presentation: { banners: null, fact_card: { amount: 5, period_label: null } } },
        "junk",
      ],
      spec_chips: ["MSFT", "MSFT", 3],
    });
    expect(view).toMatchObject({ runtime: null, turn_count: 1, max_turns: 25, spec_chips: ["MSFT"] });
    const [turn] = view.turns;
    expect(turn.presentation).toMatchObject({
      banners: [],
      evidence: [],
      disclosures: [],
      citations: [],
      traces: [],
      table: null,
      chart: null,
      fact_card: { amount: "5", period_label: "", ticker: "" },
    });
    expect(turn.candidate_slugs).toEqual([]);
  });

  it("reads why a chip keeps no remove, and drops a reason that is not text", () => {
    const view = readThreadView({
      thread_id: "t",
      spec_chip_edits: [
        { label: "MSFT", kind: "company", remove: null, keep: "The only company here." },
        { label: "Last 4 quarters", kind: "period", remove: "latest quarter", keep: 3 },
      ],
    });
    expect(view.spec_chip_edits).toEqual([
      { label: "MSFT", kind: "company", remove: null, keep: "The only company here." },
      { label: "Last 4 quarters", kind: "period", remove: "latest quarter", keep: null },
    ]);
  });

  it("drops a chart of a kind it cannot draw and evens out a trace pair", () => {
    const [turn] = readThreadView({
      thread_id: "t",
      turns: [
        {
          presentation: {
            chart: { kind: "pie" },
            traces: [{ header: "Step", inputs: [["only"]], outputs: null }],
          },
        },
      ],
    }).turns;
    expect(turn.presentation.chart).toBeNull();
    expect(turn.presentation.traces).toEqual([{ header: "Step", inputs: [["only", ""]], outputs: [] }]);
  });

  it("reads a table's exact-figure rows as text, an unreadable row as empty, and skips the keys it lacks", () => {
    const [turn] = readThreadView({
      thread_id: "t",
      turns: [
        {
          presentation: {
            table: {
              headers: ["Company", "Revenue"],
              rows: [["Apple", "$94.0B"], "junk"],
              raw: [[1, "94036000000"], null, ["x"]],
              raw_percent: [["", 0.5]],
            },
          },
        },
      ],
    }).turns;
    expect(turn.presentation.table).toEqual({
      headers: ["Company", "Revenue"],
      keys: [],
      rows: [["Apple", "$94.0B"]],
      numbers: [],
      raw: [["1", "94036000000"], [], ["x"]],
      raw_percent: [["", "0.5"]],
    });
  });

  it("keeps a line chart's amounts that are text and evidence that is an index, dropping the rest", () => {
    const [turn] = readThreadView({
      thread_id: "t",
      turns: [
        {
          presentation: {
            chart: {
              kind: "line",
              amounts: [{ AAPL: "$94.0B", MSFT: 7, note: null }, "junk"],
              evidence: [{ AAPL: 0, MSFT: -1, GOOG: 2.5, note: "1" }, null],
            },
          },
        },
      ],
    }).turns;
    expect(turn.presentation.chart).toMatchObject({
      kind: "line",
      amounts: [{ AAPL: "$94.0B" }, {}],
      evidence: [{ AAPL: 0 }, {}],
    });
  });
});

describe("readTurnEvent", () => {
  it("reports malformed JSON as an unreadable reply", () => {
    expect(() => readTurnEvent("progress", "{not json")).toThrow(BAD_RESPONSE);
  });

  it("skips events it does not know and progress it cannot read", () => {
    expect(readTurnEvent("weird", "{}")).toBeNull();
    expect(readTurnEvent("progress", '{"done": "NaN", "total": null}')).toBeNull();
    expect(readTurnEvent("progress", '{"done": 1, "total": 3}')).toEqual({
      event: "progress",
      data: { done: 1, total: 3 },
    });
  });

  it("refuses a thread event without a thread", () => {
    expect(() => readTurnEvent("thread", "null")).toThrow(BAD_RESPONSE);
    expect(() => readTurnEvent("thread", "{}")).toThrow(BAD_RESPONSE);
  });
});

describe("runTurn", () => {
  afterEach(() => vi.unstubAllGlobals());

  function stream(body: string, type = "text/event-stream") {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(body, { status: 200, headers: { "content-type": type } })),
    );
  }

  async function drain() {
    const events = [];
    for await (const event of runTurn("t", "q")) events.push(event);
    return events;
  }

  it("calls a JSON reply where a stream was due unreadable", async () => {
    stream('{"ok": true}', "application/json");
    await expect(drain()).rejects.toMatchObject({ message: BAD_RESPONSE });
  });

  it("says the connection closed when the stream ends without an answer", async () => {
    stream("event: weird\ndata: {}\n\n");
    await expect(drain()).rejects.toMatchObject({ status: 502, message: /connection closed/ });
  });
});

describe("thread calls", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("passes on how long a refused thread creation should wait", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ detail: "Slow down." }), {
            status: 429,
            headers: { "retry-after": "600" },
          }),
      ),
    );
    const refused = await createThread().catch((error: unknown) => error);
    expect(refused).toBeInstanceOf(ApiError);
    expect(refused).toMatchObject({ status: 429, retryAfter: 600 });
  });

  it("checks a fetched thread's shape", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 200 })));
    await expect(getThread("t")).rejects.toMatchObject({ message: BAD_RESPONSE });
  });
});
