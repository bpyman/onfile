import { createSseParser } from "./sse";
import type {
  ChartSpec,
  CreatedThread,
  DisplayTable,
  DisplayTrace,
  LineChartSpec,
  Meta,
  Pair,
  Presentation,
  QuarterlyFactCard,
  QuickActions,
  RuntimeGuide,
  RuntimeKind,
  ThreadView,
  Turn,
  TurnEvent,
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    /** Seconds the server asked to wait (Retry-After), when it said. */
    readonly retryAfter: number | null = null,
  ) {
    super(message);
  }
}

/** The service answered, but not in a shape the window can read. */
export const BAD_RESPONSE = "The analysis service sent a reply the window couldn't read. Please try again.";
const CLOSED_EARLY = "The connection closed before the analysis finished.";

function badResponse(): ApiError {
  return new ApiError(BAD_RESPONSE, 502);
}

function retryAfter(response: Response): number | null {
  const seconds = Number(response.headers.get("retry-after"));
  return Number.isFinite(seconds) && seconds > 0 ? seconds : null;
}

async function detail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // fall through
  }
  return response.status >= 500
    ? "The analysis service is unavailable. Please try again."
    : `Request failed (${response.status}).`;
}

async function failure(response: Response): Promise<ApiError> {
  return new ApiError(await detail(response), response.status, retryAfter(response));
}

async function json<T>(input: string, read: (raw: unknown) => T, init?: RequestInit): Promise<T> {
  const response = await fetch(input, { cache: "no-store", ...init });
  if (!response.ok) throw await failure(response);
  let raw: unknown;
  try {
    raw = await response.json();
  } catch {
    // A cut-off or non-JSON body is the service's fault, not the network's.
    throw badResponse();
  }
  return read(raw);
}

/** Storefront copy; `runtime` picks whose snapshot banner to report (the deployment default when omitted). */
export function getMeta(runtime?: RuntimeKind): Promise<Meta> {
  return json(runtime ? `/api/meta?runtime=${runtime}` : "/api/meta", readMeta);
}

/**
 * Wake the hosted API while the visitor reads the landing page (ADR 0006).
 * True once it answers, so a slow turn after that is not called a wake-up.
 */
export function pingHealth(): Promise<boolean> {
  return fetch("/api/health", { cache: "no-store" }).then(
    (response) => response.ok,
    () => false,
  );
}

/** Start a thread bound to `runtime` (the deployment default when omitted). */
export function createThread(runtime?: RuntimeKind): Promise<CreatedThread> {
  return json("/api/threads", readCreatedThread, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(runtime ? { runtime } : {}),
  });
}

export function getThread(threadId: string): Promise<ThreadView> {
  return json(`/api/threads/${encodeURIComponent(threadId)}`, readThreadView);
}

export async function deleteThread(threadId: string): Promise<void> {
  const response = await fetch(`/api/threads/${encodeURIComponent(threadId)}`, {
    method: "DELETE",
  });
  if (!response.ok && response.status !== 404) throw await failure(response);
}

/** POST a turn on the thread's own runtime and yield server-sent events until `thread` or `error`. */
export async function* runTurn(
  threadId: string,
  message: string,
  signal?: AbortSignal,
): AsyncGenerator<TurnEvent> {
  const response = await fetch(`/api/threads/${encodeURIComponent(threadId)}/turns`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ message }),
    signal,
  });
  if (!response.ok) throw await failure(response);
  const kind = (response.headers.get("content-type") ?? "").split(";")[0].trim();
  if (!response.body || kind !== "text/event-stream") {
    await response.body?.cancel();
    throw badResponse();
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  const parse = createSseParser();
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      for (const message of parse(value)) {
        const event = readTurnEvent(message.event, message.data);
        // An event this window does not know (a newer API) is skipped, not fatal.
        if (!event) continue;
        yield event;
        if (event.event === "thread" || event.event === "error") return;
      }
    }
  } finally {
    reader.releaseLock();
  }
  throw new ApiError(CLOSED_EARLY, 502);
}

/** One server-sent event, checked; null for a kind the window does not know. */
export function readTurnEvent(name: string, data: string): TurnEvent | null {
  if (!["progress", "thread", "error"].includes(name)) return null;
  let raw: unknown;
  try {
    raw = JSON.parse(data);
  } catch {
    throw badResponse();
  }
  if (name === "thread") return { event: "thread", data: readThreadView(raw) };
  const body = record(raw);
  if (name === "error") {
    return { event: "error", data: { message: text(body.message) || "The analysis could not be completed." } };
  }
  const done = count(body.done);
  const total = count(body.total);
  return done === null || total === null ? null : { event: "progress", data: { done, total } };
}

// ---------------------------------------------------------------------------
// Reading the API's JSON. The server pins these shapes (tests/test_api.py), but
// a stored thread can predate a field and a proxy can mangle a reply: a missing
// list becomes empty and a missing string blank, so one odd answer cannot take
// the window down. Only what the window cannot do without (an id) is refused.

type Raw = Record<string, unknown>;

function record(value: unknown): Raw {
  return isRecord(value) ? value : {};
}

function isRecord(value: unknown): value is Raw {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function text(value: unknown): string {
  return typeof value === "string" ? value : typeof value === "number" ? String(value) : "";
}

function textOrNull(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function texts(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function list<T>(items: unknown, read: (item: Raw, index: number) => T | null): T[] {
  if (!Array.isArray(items)) return [];
  return items.flatMap((item, index) => {
    if (!isRecord(item)) return [];
    const value = read(item, index);
    return value === null ? [] : [value];
  });
}

/** A count from the server: a finite number at least zero, else null. */
function count(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
}

function strings<K extends string>(raw: Raw, keys: readonly K[]): Record<K, string> {
  return Object.fromEntries(keys.map((key) => [key, text(raw[key])])) as Record<K, string>;
}

export function runtimeKind(value: unknown): RuntimeKind | null {
  return value === "recorded" || value === "live" ? value : null;
}

export function readCreatedThread(raw: unknown): CreatedThread {
  const body = record(raw);
  const threadId = text(body.thread_id);
  const runtime = runtimeKind(body.runtime);
  if (!threadId || !runtime) throw badResponse();
  return { thread_id: threadId, runtime, notice: textOrNull(body.notice) };
}

export function readThreadView(raw: unknown): ThreadView {
  const body = record(raw);
  const threadId = text(body.thread_id);
  if (!threadId) throw badResponse();
  const turns = list(body.turns, readTurn);
  return {
    thread_id: threadId,
    runtime: runtimeKind(body.runtime),
    turns,
    spec_chips: [...new Set(texts(body.spec_chips))],
    spec_chip_edits: list(body.spec_chip_edits, (item) => {
      const label = text(item.label);
      const kind = CHIP_KINDS.find((each) => each === item.kind) ?? "period";
      return label
        ? { label, kind, remove: textOrNull(item.remove) || null, keep: textOrNull(item.keep) || null }
        : null;
    }),
    quick_actions: readQuickActions(record(body.quick_actions)),
    pending_clarification: body.pending_clarification === true,
    turn_count: count(body.turn_count) ?? turns.length,
    max_turns: count(body.max_turns) || 25,
    turn_in_flight: body.turn_in_flight === true,
  };
}

const CHIP_KINDS = ["company", "constituents", "metric", "period", "operation"] as const;

function readQuickActions(raw: Raw): QuickActions {
  const actions = (value: unknown) =>
    list(value, (item) => {
      const action = { label: text(item.label), message: text(item.message) };
      return action.label && action.message ? action : null;
    });
  return { company: actions(raw.company), metric: actions(raw.metric), period: actions(raw.period) };
}

function readTurn(raw: Raw, position: number): Turn {
  return {
    index: count(raw.index) ?? position,
    message: text(raw.message),
    presentation: readPresentation(record(raw.presentation)),
    candidate_slugs: texts(raw.candidate_slugs),
    clarify_enabled: raw.clarify_enabled === true,
  };
}

const FACT_CARD_KEYS = [
  "company_name",
  "ticker",
  "metric_header",
  "amount",
  "period_label",
  "form",
  "accession_number",
  "concept",
  "source_url",
] as const;
const DIRECTIONS = ["up", "down", "flat"] as const;

function readFactCard(raw: Raw): QuarterlyFactCard {
  return {
    ...strings(raw, FACT_CARD_KEYS),
    kind_label: text(raw.kind_label),
    concept_short: text(raw.concept_short),
    changes: list(raw.changes, (item) => {
      const label = text(item.label);
      const direction = DIRECTIONS.find((each) => each === item.direction) ?? "flat";
      return label ? { label, direction, title: text(item.title) } : null;
    }),
  };
}

const EVIDENCE_KEYS = [
  "label",
  "amount",
  "raw_amount",
  "company_name",
  "ticker",
  "cik",
  "concept",
  "period_label",
  "accession_number",
  "form",
  "source_url",
  "selection_rule",
] as const;
const DISCLOSURE_KEYS = [
  "section_label",
  "change_kind",
  "before_text",
  "after_text",
  "older_accession",
  "newer_accession",
  "older_url",
  "newer_url",
] as const;

export function readPresentation(raw: Raw): Presentation {
  return {
    intent: text(raw.intent),
    intent_label: text(raw.intent_label),
    banners: texts(raw.banners),
    traces: list(raw.traces, readTrace),
    citations: list(raw.citations, (item, index) => ({
      index: count(item.index) ?? index + 1,
      title: text(item.title),
      url: text(item.url),
      published: textOrNull(item.published),
    })),
    fact_card: isRecord(raw.fact_card) ? readFactCard(raw.fact_card) : null,
    table: isRecord(raw.table) ? readTable(raw.table) : null,
    chart: isRecord(raw.chart) ? readChart(raw.chart) : null,
    evidence: list(raw.evidence, (item) => ({
      ...strings(item, EVIDENCE_KEYS),
      ...(typeof item.exact_amount === "string" ? { exact_amount: item.exact_amount } : {}),
    })),
    disclosures: list(raw.disclosures, (item) => ({
      ...strings(item, DISCLOSURE_KEYS),
      ...(typeof item.subsection === "string" ? { subsection: item.subsection } : {}),
    })),
    essay: textOrNull(raw.essay),
    message: textOrNull(raw.message),
    candidates: texts(raw.candidates),
    clarify_prompt: textOrNull(raw.clarify_prompt),
    suggestions: texts(raw.suggestions),
    message_tone: raw.message_tone === "warning" ? "warning" : "info",
    headline: textOrNull(raw.headline),
    trends: list(raw.trends, (item) => {
      const chart = readChart(item);
      return chart?.kind === "line" ? chart : null;
    }),
  };
}

function readPairs(value: unknown): Pair[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((pair) => (Array.isArray(pair) ? [[text(pair[0]), text(pair[1])] as Pair] : []));
}

function readTrace(raw: Raw): DisplayTrace {
  return { header: text(raw.header), inputs: readPairs(raw.inputs), outputs: readPairs(raw.outputs) };
}

function readTable(raw: Raw): DisplayTable {
  const headers = texts(raw.headers);
  const rows = Array.isArray(raw.rows) ? raw.rows.filter(Array.isArray).map((row) => row.map(text)) : [];
  const numbers = Array.isArray(raw.numbers)
    ? raw.numbers.map((row) =>
        Array.isArray(row) ? row.map((n) => (typeof n === "number" && Number.isFinite(n) ? n : null)) : [],
      )
    : [];
  return {
    headers,
    keys: texts(raw.keys),
    rows,
    numbers,
    ...(Array.isArray(raw.row_keys) ? { row_keys: texts(raw.row_keys) } : {}),
    ...(Array.isArray(raw.evidence) ? { evidence: raw.evidence.map(indices) } : {}),
    ...(Array.isArray(raw.raw) ? { raw: textRows(raw.raw) } : {}),
    ...(Array.isArray(raw.raw_percent) ? { raw_percent: textRows(raw.raw_percent) } : {}),
  };
}

/** Rows of text; a row that is not a list is read as an empty one. */
function textRows(value: unknown): string[][] {
  return Array.isArray(value) ? value.map((row) => (Array.isArray(row) ? row.map(text) : [])) : [];
}

/** The entries of a record whose values pass `guard`; anything but a record is empty. */
function recordOf<T>(value: unknown, guard: (candidate: unknown) => candidate is T): Record<string, T> {
  return Object.fromEntries(
    Object.entries(record(value)).filter((entry): entry is [string, T] => guard(entry[1])),
  );
}

function isText(value: unknown): value is string {
  return typeof value === "string";
}

/** A row of evidence indices: whole numbers at least zero, else null. */
function indices(row: unknown): (number | null)[] {
  return Array.isArray(row) ? row.map((n) => (isIndex(n) ? n : null)) : [];
}

function isIndex(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

const VALUE_KINDS = ["usd", "percent", "multiple", "per_share"] as const;

function readChart(raw: Raw): ChartSpec | null {
  const base = {
    title: text(raw.title),
    metric: text(raw.metric),
    metric_label: text(raw.metric_label),
    value_kind: VALUE_KINDS.find((kind) => kind === raw.value_kind) ?? "usd",
    caption: text(raw.caption),
    horizontal: raw.horizontal === true,
    ...(typeof raw.resorted_caption === "string" ? { resorted_caption: raw.resorted_caption } : {}),
  };
  if (raw.kind === "bar") {
    return {
      ...base,
      kind: "bar",
      // Value stays as sent: a bar without a finite one is drawn as missing (chart-data).
      records: list(raw.records, (item) => ({
        ...(typeof item.Key === "string" ? { Key: item.Key } : {}),
        Company: text(item.Company),
        Value: item.Value as number,
        Amount: text(item.Amount),
        Label: text(item.Label),
        Missing: item.Missing === true,
        ...(typeof item.Period === "string" ? { Period: item.Period } : {}),
        ...(isIndex(item.Evidence) ? { Evidence: item.Evidence } : {}),
        Derived: item.Derived === true,
      })),
    };
  }
  if (raw.kind === "line") {
    const line: LineChartSpec = {
      ...base,
      kind: "line",
      records: list(raw.records, (item) => item as LineChartSpec["records"][number]),
      period_labels: Array.isArray(raw.period_labels) ? raw.period_labels.map(text) : [],
      series: texts(raw.series),
      amounts: Array.isArray(raw.amounts) ? raw.amounts.map((item) => recordOf(item, isText)) : [],
      ...(Array.isArray(raw.series_labels) ? { series_labels: raw.series_labels.map(text) } : {}),
      ...(Array.isArray(raw.evidence) ? { evidence: raw.evidence.map((item) => recordOf(item, isIndex)) } : {}),
      ...(Array.isArray(raw.derived) ? { derived: raw.derived.map(texts) } : {}),
    };
    return line;
  }
  return null;
}

function readGuide(value: unknown): RuntimeGuide | undefined {
  if (!isRecord(value)) return undefined;
  const runtimes = list(value.runtimes, (item) => {
    const kind = runtimeKind(item.kind);
    return kind ? { kind, name: text(item.name), points: texts(item.points) } : null;
  });
  return runtimes.length ? { runtimes, footer: text(value.footer) } : undefined;
}

export function readMeta(raw: unknown): Meta {
  const body = record(raw);
  const runtime = record(body.runtime);
  const fallback = runtimeKind(runtime.default);
  // Without the deployment's runtime the window cannot label anything; say so.
  if (!fallback) throw badResponse();
  const copy = record(body.runtime_copy);
  const snapshot = record(body.snapshot);
  const maxChars = count(body.max_message_chars);
  return {
    runtime: { default: fallback, locked: runtime.locked === true },
    runtime_copy: { recorded: text(copy.recorded), live: text(copy.live), locked: text(copy.locked) },
    runtime_guide: readGuide(body.runtime_guide),
    snapshot: text(snapshot.banner) ? { banner: text(snapshot.banner), stale: snapshot.stale === true } : null,
    example_query: text(body.example_query),
    guided_stories: list(body.guided_stories, (item) => {
      const story = { label: text(item.label), question: text(item.question) };
      return story.label && story.question ? story : null;
    }),
    capabilities: list(body.capabilities, (item) => {
      const description = text(item.description);
      return description ? { description, examples: texts(item.examples) } : null;
    }),
    metric_groups: list(body.metric_groups, (item) => {
      const title = text(item.title);
      return title ? { title, names: texts(item.names) } : null;
    }),
    max_message_chars: maxChars && maxChars >= 1 ? Math.floor(maxChars) : null,
  };
}
