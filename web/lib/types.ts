// Mirrors financial_analyst_agent.presentation dataclasses as serialised by
// financial_analyst_agent.api. tests/test_api.py pins the key set.

export type Pair = [label: string, value: string];

/** A fact's change on its card ("▲17.7% YoY"); `direction` colours the arrow only. */
export interface ChangeChip {
  label: string;
  direction: "up" | "down" | "flat";
  /** What the change was measured against. */
  title: string;
}

export interface QuarterlyFactCard {
  company_name: string;
  ticker: string;
  metric_header: string;
  amount: string;
  period_label: string;
  form: string;
  accession_number: string;
  concept: string;
  source_url: string;
  /** "Quarterly fact", "Calculated", "Derived quarter" or "Balance sheet"; empty in older answers. */
  kind_label: string;
  /** The concept cut to a few words; empty in older answers. */
  concept_short: string;
  changes: ChangeChip[];
}

export interface DisplayTable {
  headers: string[];
  keys: string[];
  rows: string[][];
  numbers: (number | null)[][];
  /** Each row's company key; bar records carry the same key. Absent in older answers. */
  row_keys?: string[];
  /** Each cell's index into the answer's evidence, or null; absent in older answers. */
  evidence?: (number | null)[][];
  /** Each cell exactly (unrounded amounts, ISO dates), for CSV; absent in older answers. */
  raw?: string[][];
  /** A change cell's percent ("16.4"), beside its amount in raw; "" elsewhere. */
  raw_percent?: string[][];
}

export interface DisplayTrace {
  header: string;
  inputs: Pair[];
  outputs: Pair[];
}

export interface DisplayCitation {
  index: number;
  title: string;
  url: string;
  published: string | null;
}

export type ValueKind = "usd" | "percent" | "multiple" | "per_share";

interface ChartBase {
  title: string;
  metric: string;
  metric_label: string;
  value_kind: ValueKind;
  caption: string;
  horizontal: boolean;
  /** The caption once the table is re-sorted, when the server's says how it ordered the bars. */
  resorted_caption?: string;
}

export interface BarRecord {
  /** The table row's company key; absent in older answers. */
  Key?: string;
  Company: string;
  Value: number;
  Amount: string;
  Label: string;
  Missing: boolean;
  Period?: string;
  /** Index into the answer's evidence; absent in older answers. */
  Evidence?: number | null;
  /** A derived (†) figure. */
  Derived?: boolean;
}

export interface BarChartSpec extends ChartBase {
  kind: "bar";
  records: BarRecord[];
}

export interface LineChartSpec extends ChartBase {
  kind: "line";
  records: Record<string, string | number | null>[];
  period_labels: string[];
  series: string[];
  amounts: Record<string, string>[];
  /** Each series' short name (ticker); absent in older answers. */
  series_labels?: string[];
  /** Each record's evidence index per series name; absent in older answers. */
  evidence?: Record<string, number>[];
  /** The series whose point in each record is derived (†). */
  derived?: string[][];
}

export type ChartSpec = BarChartSpec | LineChartSpec;

export interface EvidenceItem {
  label: string;
  amount: string;
  raw_amount: string;
  /** raw_amount grouped for reading; absent from older stored answers. */
  exact_amount?: string;
  company_name: string;
  ticker: string;
  cik: string;
  concept: string;
  period_label: string;
  accession_number: string;
  form: string;
  source_url: string;
  selection_rule: string;
}

export interface DisplayDisclosure {
  section_label: string;
  change_kind: string;
  before_text: string;
  after_text: string;
  older_accession: string;
  newer_accession: string;
  older_url: string;
  newer_url: string;
  /** The heading the change sits under; absent in older answers. */
  subsection?: string;
}

export interface Presentation {
  intent: string;
  intent_label: string;
  banners: string[];
  traces: DisplayTrace[];
  citations: DisplayCitation[];
  fact_card: QuarterlyFactCard | null;
  table: DisplayTable | null;
  chart: ChartSpec | null;
  evidence: EvidenceItem[];
  disclosures: DisplayDisclosure[];
  essay: string | null;
  message: string | null;
  candidates: string[];
  /** The question a clarification asks; null unless candidates are offered. */
  clarify_prompt: string | null;
  /** Next questions offered as one-tap chips, in words the planner reads. */
  suggestions: string[];
  /** "info" for a guide reply (help, greetings), "warning" for a refusal. */
  message_tone: "info" | "warning";
  /** One sentence that answers the question before the table, or null. */
  headline?: string | null;
  /** Small trend charts beside one company's overview; empty for any other answer. */
  trends: LineChartSpec[];
}

export interface Turn {
  index: number;
  message: string;
  presentation: Presentation;
  candidate_slugs: string[];
  clarify_enabled: boolean;
}

/** The provider set a thread is bound to for its whole life. */
export type RuntimeKind = "recorded" | "live";

/** POST /api/threads. `notice` is set when the deployment served another runtime. */
export interface CreatedThread {
  thread_id: string;
  runtime: RuntimeKind;
  notice: string | null;
}

/** An active-analysis chip, and the follow-up its × sends (null: no ×). */
export interface ChipEdit {
  label: string;
  kind: "company" | "constituents" | "metric" | "period" | "operation";
  remove: string | null;
  /** Why the chip has no ×, said on hover: the last company or metric, or a ranking. */
  keep?: string | null;
}

/** A follow-up the active analysis's "+" offers. */
export interface QuickAction {
  label: string;
  message: string;
}

export interface QuickActions {
  company: QuickAction[];
  metric: QuickAction[];
  period: QuickAction[];
}

export interface ThreadView {
  thread_id: string;
  /** null until the thread is bound (a thread saved before binding existed). */
  runtime: RuntimeKind | null;
  turns: Turn[];
  spec_chips: string[];
  /** The chips with their kinds and × follow-ups; empty from an older API. */
  spec_chip_edits?: ChipEdit[];
  quick_actions?: QuickActions;
  pending_clarification: boolean;
  turn_count: number;
  max_turns: number;
  /** A turn is running on this thread (a reload mid-turn polls until it ends). */
  turn_in_flight: boolean;
}

/** What each runtime answers from, for the status line's "How runtimes differ". */
export interface RuntimeGuide {
  runtimes: { kind: RuntimeKind; name: string; points: string[] }[];
  footer: string;
}

export interface Meta {
  /** The runtime a new thread gets, and whether the deployment serves only the recorded one. */
  runtime: { default: RuntimeKind; locked: boolean };
  /** Status-line copy per runtime, and the tooltip for a locked runtime switch. */
  runtime_copy: { recorded: string; live: string; locked: string };
  /** Absent from an older API. */
  runtime_guide?: RuntimeGuide;
  /** null when the API sent no banner. */
  snapshot: { banner: string; stale: boolean } | null;
  example_query: string;
  guided_stories: { label: string; question: string }[];
  capabilities: { description: string; examples: string[] }[];
  metric_groups: { title: string; names: string[] }[];
  /** null when the API sent no usable limit; the window keeps its own. */
  max_message_chars: number | null;
}

export type TurnEvent =
  | { event: "progress"; data: { done: number; total: number } }
  | { event: "thread"; data: ThreadView }
  | { event: "error"; data: { message: string } };
