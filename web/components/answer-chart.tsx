"use client";

import { useId, useMemo, useState, type ReactNode } from "react";
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
  Rectangle,
  ReferenceLine,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from "recharts";
import type { BarShapeProps } from "recharts/types/cartesian/Bar";
import type { ActiveDotProps, DotItemDotProps } from "recharts/types/util/types";
import {
  barRows,
  barTicks,
  DENSE_PERIODS,
  orderedBars,
  calendarsDiffer,
  endLabelSides,
  lineRows,
  lineSeries,
  niceTicks,
  quarterTicks,
  splitPeriod,
  tickLine,
  valueDomain,
  type BarRow,
  type LineRow,
  type LineSeries,
} from "@/lib/chart-data";
import { axisTick, cn } from "@/lib/format";
import { emphasis, NO_LEGEND, toggleSeries, type LegendState } from "@/lib/legend";
import { SNAPSHOT_HELP } from "@/lib/notes";
import type { BarChartSpec, ChartSpec, LineChartSpec, ValueKind } from "@/lib/types";
import { useInspect } from "./inspect-context";
import { SectionLabel } from "./ui";
import { usePhone } from "@/lib/browser";

/**
 * A trend line or comparison bars. Marks are placed from the server's numbers;
 * every amount written on or beside a mark is the server's string (ADR 0006).
 * ``order``: the answer table's sorted company keys; bars follow it, a trend keeps time order.
 */
export function AnswerChart({
  chart,
  order = null,
  sortNote = null,
  compact = false,
  bare = false,
  captionNote = null,
}: {
  chart: ChartSpec;
  order?: string[] | null;
  /** What the table is sorted by, when it is: bars follow it, a trend keeps time. */
  sortNote?: string | null;
  /** A small trend beside an overview: shorter, and the company goes unnamed. */
  compact?: boolean;
  /** Inside the answer card: no border of its own. */
  bare?: boolean;
  /** A note the caption ends with: the ranking snapshot's timestamp. */
  captionNote?: string | null;
}) {
  const single =
    !compact && chart.kind === "line" && chart.series.length === 1 ? chart.series[0] : null;
  const [legend, setLegend] = useState<LegendState>(NO_LEGEND);
  // Built once per chart: hovering the legend re-renders without rebuilding the rows.
  const series = useMemo(() => (chart.kind === "line" ? lineSeries(chart) : []), [chart]);
  const rows = useMemo(() => (chart.kind === "line" ? lineRows(chart) : []), [chart]);
  const bars = useMemo(() => (chart.kind === "bar" ? barRows(chart) : []), [chart]);
  const derived = rows.some((row) => row.derived.length > 0);
  // Bars that follow the table's sort are no longer in the server's order.
  const caption = chart.kind === "bar" && order && chart.resorted_caption ? chart.resorted_caption : chart.caption;
  return (
    <figure
      aria-label={`${chart.title}: ${chart.metric_label}`}
      className={cn("overflow-hidden", !bare && "rounded-xl border border-border bg-surface")}
    >
      <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2.5 px-4 pt-4 sm:px-5">
        <div className="min-w-0">
          <SectionLabel>{chart.title}</SectionLabel>
          <div className="mt-1 flex min-w-0 flex-wrap items-baseline gap-x-2 text-[15px] font-medium text-fg">
            {chart.metric_label}
            {single && <span className="truncate text-[13px] font-normal text-muted">{single}</span>}
          </div>
        </div>
        {series.length > 1 && (
          <Legend
            series={series}
            state={legend}
            onChange={setLegend}
            derived={derived}
          />
        )}
        {series.length === 1 && derived && !compact && <DerivedKey />}
        {sortNote && (
          <p className="w-full text-[11.5px] text-muted">
            {chart.kind === "line"
              ? `In time order; the table below is sorted by ${sortNote}.`
              : `Ordered as the table: ${sortNote}.`}
          </p>
        )}
      </header>
      <div className={cn("px-1 pb-3 sm:px-3", compact ? "pt-2" : "pt-4")}>
        {chart.kind === "line" ? (
          <TrendChart
            chart={chart}
            rows={rows}
            series={series}
            height={compact ? 150 : 280}
            compact={compact}
            legend={legend}
          />
        ) : (
          // A new order draws the bars afresh: animating heights between orders
          // would pair each label with another company's bar for a moment.
          <ComparisonChart key={order?.join("|") ?? "server"} chart={chart} bars={bars} order={order} />
        )}
      </div>
      <ChartSummary bars={bars} rows={rows} series={series} />
      {(caption || captionNote) && (
        <figcaption className="border-t border-border bg-surface-2/40 px-4 py-2.5 text-xs leading-relaxed text-muted sm:px-5">
          {caption}
          {caption && captionNote ? " " : ""}
          {captionNote && (
            <span
              className="cursor-help text-subtle"
              title={SNAPSHOT_HELP}
            >
              {captionNote}.
            </span>
          )}
        </figcaption>
      )}
    </figure>
  );
}

/**
 * The chart's points as text for a screen reader, in place of the plot: one
 * line per bar, or per series with each period's amount (a chart has rows of
 * one kind, so the other list is empty).
 */
function ChartSummary({ bars, rows, series }: { bars: BarRow[]; rows: LineRow[]; series: LineSeries[] }) {
  return (
    <ul className="sr-only">
      {bars.map((row, index) => (
        <li key={`${row.key}-${index}`}>{`${row.name}: ${row.missing ? row.label : row.amount || row.label}`}</li>
      ))}
      {series.map(({ key, name }) => (
        <li key={key}>
          {`${name}: ${rows.map((row) => `${row.period} ${row.amounts[key] ?? "no value"}`).join("; ")}`}
        </li>
      ))}
    </ul>
  );
}

/**
 * The series, each a button: pointing at one (or focusing it) brings its line
 * forward and dims the rest; pressing it hides or shows the line.
 */
function Legend({
  series,
  state,
  onChange,
  derived,
}: {
  series: LineSeries[];
  state: LegendState;
  onChange: (state: LegendState) => void;
  derived: boolean;
}) {
  const all = series.map(({ key }) => key);
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
      <ul aria-label="Series" className="flex flex-wrap items-center gap-x-1 gap-y-1 text-xs text-muted" onMouseLeave={() => onChange({ ...state, focus: null })}>
        {series.map(({ key, name, label, color }) => {
          const hidden = state.hidden.includes(key);
          return (
            <li key={key}>
              <button
                type="button"
                aria-pressed={!hidden}
                title={`${name}: ${hidden ? "show" : "hide"} its line`}
                onClick={() => onChange(toggleSeries(state, key, all))}
                onMouseEnter={() => onChange({ ...state, focus: key })}
                onFocus={() => onChange({ ...state, focus: key })}
                onBlur={() => onChange({ ...state, focus: null })}
                className={cn(
                  "inline-flex h-7 items-center gap-1.5 rounded-md px-1.5 transition-[color,opacity,background] hover:bg-surface-2 hover:text-fg",
                  hidden && "opacity-45 line-through decoration-subtle",
                )}
              >
                <LineKey color={color} />
                {/* A phone names each series by its ticker; a wider screen by its name. */}
                <span className="sm:hidden">{label}</span>
                <span className="hidden sm:inline">{name}</span>
              </button>
            </li>
          );
        })}
      </ul>
      {derived && <DerivedKey />}
    </div>
  );
}

/** What a hollow point means. */
function DerivedKey() {
  return (
    <span className="inline-flex items-center gap-1.5 text-[11.5px] text-subtle" title="Derived from reported figures: the filings do not report this quarter on its own">
      <svg aria-hidden viewBox="0 0 10 10" className="size-2.5">
        <circle cx="5" cy="5" r="3.6" fill="none" stroke="currentColor" strokeWidth="1.6" />
      </svg>
      Derived †
    </span>
  );
}

function LineKey({ color }: { color: string }) {
  return <span aria-hidden className="h-0.5 w-3.5 shrink-0 rounded-full" style={{ background: color }} />;
}

const AXIS_TICK = { fill: "var(--subtle)", fontSize: 11 } as const;
const GRID = "var(--border)";
function TrendChart({
  chart,
  rows,
  series,
  height,
  compact,
  legend,
}: {
  chart: LineChartSpec;
  rows: LineRow[];
  series: LineSeries[];
  height: number;
  compact: boolean;
  legend: LegendState;
}) {
  const gradientId = useId().replace(/:/g, "");
  const inspect = useInspect();
  const phone = usePhone();
  const shown = series.filter(({ key }) => !legend.hidden.includes(key));
  const values = rows.flatMap((row) => shown.map(({ key }) => row[key] as number | null));
  // A small trend needs only its floor, middle and top.
  const ticks = niceTicks(valueDomain(values, { zero: false }), compact ? 3 : 5);
  const domain: [number, number] = [ticks[0], ticks[ticks.length - 1]];
  const endLabels = endLabelsFit(rows, shown, domain) ? endLabelSides(rows, shown, domain) : null;
  const lone = series.length === 1 ? series[0] : null;
  // Companies on different fiscal calendars: each quarter at its own date.
  const staggered = series.length > 1 && calendarsDiffer(rows);
  // Many quarters on a phone collide: let the axis drop labels that do not fit,
  // measured by the label's wider line and always keeping the newest.
  const dense = rows.length > DENSE_PERIODS;
  const pinned = phone && !compact;
  const pinHeight = 44 + 18 * Math.min(shown.length, 5);
  const open = (index: number | undefined) => {
    if (inspect && typeof index === "number") inspect(index);
  };
  return (
    <div className="relative" style={pinned ? { paddingBottom: pinHeight } : undefined}>
      {pinned && (
        <p aria-hidden className="absolute inset-x-3 bottom-2 text-center text-[11.5px] text-subtle">
          Tap a point to read its values
        </p>
      )}
      <ComposedChart
        responsive
        // The plot is drawn for the eye; ChartSummary reads it out, so no tab stops per point.
        accessibilityLayer={false}
        data={rows}
        margin={{ top: 22, right: series.length > 1 ? 28 : 20, bottom: 4, left: 4 }}
        style={{ width: "100%", height }}
      >
        {lone && (
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={lone.color} stopOpacity={0.16} />
              <stop offset="100%" stopColor={lone.color} stopOpacity={0} />
            </linearGradient>
          </defs>
        )}
        <CartesianGrid vertical={false} stroke={GRID} />
        {staggered ? (
          <XAxis
            dataKey="time"
            type="number"
            scale="time"
            domain={["dataMin", "dataMax"]}
            ticks={quarterTicks(rows)}
            tickLine={false}
            axisLine={{ stroke: GRID }}
            tick={<QuarterTick />}
            tickFormatter={(time: number) => MONTHS[new Date(time).getUTCMonth()]}
            interval={dense ? "preserveEnd" : 0}
            minTickGap={6}
            height={40}
            padding={{ left: 24, right: 24 }}
          />
        ) : (
          <XAxis
            dataKey="period"
            tickLine={false}
            axisLine={{ stroke: GRID }}
            tick={<PeriodTick />}
            tickFormatter={(period: string) => tickLine(String(period))}
            interval={dense ? "preserveEnd" : 0}
            minTickGap={6}
            height={40}
            padding={{ left: 24, right: 24 }}
          />
        )}
        <YAxis
          tickFormatter={(value: number) => axisTick(value, chart.value_kind)}
          tick={AXIS_TICK}
          tickLine={false}
          axisLine={false}
          domain={domain}
          ticks={ticks}
          interval={0}
          width={56}
        />
        {domain[0] < 0 && domain[1] > 0 && (
          // Growth that turns negative: zero is the line that matters.
          <ReferenceLine y={0} stroke="var(--border-strong)" strokeWidth={1} ifOverflow="extendDomain" />
        )}
        <Tooltip
          cursor={{ stroke: "var(--border-strong)", strokeWidth: 1 }}
          // Beside the pointer, not pinned to the top where the peaks are drawn; on a phone, under the plot.
          offset={16}
          {...(pinned ? { position: { x: 4, y: height + 2 }, allowEscapeViewBox: { x: false, y: true } } : {})}
          content={(props) => (
            <TrendTooltip
              {...props}
              // A time axis row holds one calendar's quarter; the others are not missing.
              series={staggered ? shown.filter(({ key }) => props.payload?.[0]?.payload?.[key] != null) : shown}
              short={series.length > 2}
              wide={pinned}
            />
          )}
          isAnimationActive={false}
        />
        {lone && (
          <Area
            dataKey={lone.key}
            type="linear"
            stroke="none"
            fill={`url(#${gradientId})`}
            baseValue={domain[0]}
            tooltipType="none"
            activeDot={false}
            isAnimationActive={false}
          />
        )}
        {shown.map(({ key, color }) =>
          !staggered && hasGap(rows, key) ? (
            // A missing quarter is bridged faintly, never drawn as a reported value.
            <Line
              key={`${key}-gap`}
              dataKey={key}
              type="linear"
              connectNulls
              stroke={color}
              strokeOpacity={emphasis(legend, key) === "dim" ? 0.15 : 0.45}
              strokeWidth={1.5}
              strokeDasharray="2 5"
              strokeLinecap="round"
              dot={false}
              activeDot={false}
              tooltipType="none"
              isAnimationActive={false}
            />
          ) : null,
        )}
        {shown.map(({ key, color, name, label }) => {
          const tone = emphasis(legend, key);
          return (
            <Line
              key={key}
              name={name}
              dataKey={key}
              type="linear"
              // On a time axis the other calendar's rows are not gaps in this line.
              connectNulls={staggered}
              stroke={color}
              strokeOpacity={tone === "dim" ? 0.22 : 1}
              strokeWidth={tone === "focus" ? 2.75 : 2}
              strokeLinecap="round"
              strokeLinejoin="round"
              dot={(props: DotItemDotProps) => (
                <TrendDot
                  key={`${key}-${props.index}`}
                  {...props}
                  seriesKey={key}
                  color={color}
                  dim={tone === "dim"}
                  endLabel={endLabels?.[key] ? { side: endLabels[key], name: shown.length > 1 ? label : null } : null}
                  onOpen={open}
                />
              )}
              activeDot={(props: ActiveDotProps) => (
                <ActiveDot key={`${key}-active`} {...props} seriesKey={key} color={color} onOpen={open} />
              )}
              animationDuration={600}
            />
          );
        })}
      </ComposedChart>
    </div>
  );
}

function hasGap(rows: LineRow[], key: string): boolean {
  const present = rows.map((row) => row[key] !== null);
  const first = present.indexOf(true);
  const last = present.lastIndexOf(true);
  return first >= 0 && present.slice(first, last + 1).includes(false);
}

/** End labels only when the latest points sit far enough apart to read. */
function endLabelsFit(rows: LineRow[], series: LineSeries[], [low, high]: [number, number]): boolean {
  const ends = series
    .map(({ key }) => rows.findLast((row) => row.last?.includes(key))?.[key])
    .filter((value): value is number => typeof value === "number")
    .sort((a, b) => a - b);
  const span = high - low || 1;
  return ends.every((value, index) => index === 0 || (value - ends[index - 1]) / span > 0.14);
}

function TrendDot({
  cx,
  cy,
  payload,
  seriesKey,
  color,
  dim,
  endLabel,
  onOpen,
}: DotItemDotProps & {
  seriesKey: string;
  color: string;
  dim: boolean;
  /** Where the series' last point puts its label, and the ticker it leads with. */
  endLabel: { side: "above" | "below"; name: string | null } | null;
  onOpen: (index: number | undefined) => void;
}) {
  const row = payload as LineRow;
  if (typeof cx !== "number" || typeof cy !== "number" || row[seriesKey] === null) return <g />;
  const isLast = row.last?.includes(seriesKey) ?? false;
  // A derived (†) quarter is drawn hollow: computed from reported figures, not reported itself.
  const derived = row.derived?.includes(seriesKey) ?? false;
  const evidence = row.evidence?.[seriesKey];
  return (
    <g opacity={dim ? 0.3 : 1}>
      <circle
        cx={cx}
        cy={cy}
        r={derived ? 3.6 : 4}
        fill={derived ? "var(--surface)" : color}
        stroke={derived ? color : "var(--surface)"}
        strokeWidth={2}
      />
      {evidence !== undefined && (
        // A target larger than the mark, so a finger finds it.
        <circle
          cx={cx}
          cy={cy}
          r={11}
          fill="transparent"
          className="cursor-pointer"
          onClick={() => onOpen(evidence)}
        >
          <title>{`${row.period}: ${row.amounts[seriesKey] ?? ""}. Show its source`}</title>
        </circle>
      )}
      {isLast && endLabel && (
        <text
          // The link preview reads these for its own large figures (scripts/capture-portfolio.ts).
          className="end-label"
          x={cx - 9}
          y={endLabel.side === "above" ? cy - 11 : cy + 19}
          textAnchor="end"
          fill="var(--fg)"
          fontSize={12}
          fontWeight={600}
          stroke="var(--surface)"
          strokeWidth={4}
          paintOrder="stroke"
          style={{ fontVariantNumeric: "tabular-nums" }}
        >
          {endLabel.name && (
            <tspan fill="var(--muted)" fontWeight={500}>
              {`${endLabel.name} `}
            </tspan>
          )}
          {row.amounts[seriesKey]}
        </text>
      )}
    </g>
  );
}

function ActiveDot({
  cx,
  cy,
  payload,
  seriesKey,
  color,
  onOpen,
}: ActiveDotProps & { seriesKey: string; color: string; onOpen: (index: number | undefined) => void }) {
  if (typeof cx !== "number" || typeof cy !== "number") return <g />;
  const row = payload as LineRow;
  const evidence = row?.evidence?.[seriesKey];
  const derived = row?.derived?.includes(seriesKey) ?? false;
  return (
    <g className={evidence !== undefined ? "cursor-pointer" : undefined} onClick={() => onOpen(evidence)}>
      <circle cx={cx} cy={cy} r={11} fill="transparent" />
      <circle
        cx={cx}
        cy={cy}
        r={5.5}
        fill={derived ? "var(--surface)" : color}
        stroke={derived ? color : "var(--surface)"}
        strokeWidth={2}
      />
    </g>
  );
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** A calendar quarter end on a time axis: "Jun" over "2026". */
function QuarterTick({ x, y, payload }: { x?: number; y?: number; payload?: { value: number } }) {
  const date = new Date(payload?.value ?? 0);
  return (
    <text x={x} y={y} textAnchor="middle" fontSize={11} fill="var(--subtle)">
      <tspan x={x} dy={14} fill="var(--muted)">
        {MONTHS[date.getUTCMonth()]}
      </tspan>
      <tspan x={x} dy={13}>
        {date.getUTCFullYear()}
      </tspan>
    </text>
  );
}

/** "Mar 31, 2026" on two lines, so four quarters fit a phone. */
function PeriodTick({ x, y, payload }: { x?: number; y?: number; payload?: { value: string } }) {
  const [day, year] = splitPeriod(payload?.value ?? "");
  return (
    <text x={x} y={y} textAnchor="middle" fontSize={11} fill="var(--subtle)">
      <tspan x={x} dy={14} fill="var(--muted)">
        {day}
      </tspan>
      {year && (
        <tspan x={x} dy={13}>
          {year}
        </tspan>
      )}
    </text>
  );
}

function TrendTooltip({
  active,
  payload,
  label,
  series,
  short,
  wide,
}: TooltipContentProps & {
  series: LineSeries[];
  /** More than two series: each named by its ticker. */
  short: boolean;
  /** Pinned under the plot on a phone: as wide as the chart. */
  wide: boolean;
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload as LineRow;
  // Largest first, so the rows read in the order the lines stack.
  const ordered = [...series].sort((a, b) => {
    const left = row[a.key];
    const right = row[b.key];
    if (typeof left !== "number") return 1;
    if (typeof right !== "number") return -1;
    return right - left;
  });
  return (
    <TooltipBox title={row.period || String(label ?? "")} wide={wide}>
      {ordered.map(({ key, name, label: ticker, color }) => (
        <div key={key} className="flex items-center gap-2.5">
          <LineKey color={color} />
          <span className="min-w-[4.5rem] text-[13px] font-semibold tabular-nums text-fg">
            {row.amounts[key] ?? <span className="font-normal text-subtle">—</span>}
            {row.derived?.includes(key) && <span className="font-normal text-subtle"> †</span>}
          </span>
          <span className="truncate text-muted">{short ? ticker : name}</span>
        </div>
      ))}
    </TooltipBox>
  );
}

function TooltipBox({ title, wide = false, children }: { title: string; wide?: boolean; children: ReactNode }) {
  return (
    <div
      className={cn(
        "rounded-lg border border-border-strong bg-surface/95 px-3 py-2.5 text-xs shadow-xl shadow-black/25 backdrop-blur-sm",
        wide ? "w-[calc(100vw-4.5rem)] max-w-[22rem]" : "max-w-[18rem]",
      )}
    >
      <div className="mb-1.5 text-[11px] font-medium text-subtle">{title}</div>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

const BAR_FILL = "var(--chart-1)";

function ComparisonChart({ chart, bars, order }: { chart: BarChartSpec; bars: BarRow[]; order: string[] | null }) {
  const rows = useMemo(() => orderedBars(bars, order), [bars, order]);
  const ticks = barTicks(rows.map((row) => (row.missing ? null : row.value)));
  // Sorted by another column, a rank number no longer matches the bar's place.
  const props = { rows, ticks, kind: chart.value_kind, metric: chart.metric_label, ranked: !order };
  return chart.horizontal ? <RankedBars {...props} /> : <ColumnBars {...props} />;
}

interface BarsProps {
  rows: BarRow[];
  ticks: number[];
  kind: ValueKind;
  metric: string;
  /** Rank numbers beside the names: only while bars keep the server's order. */
  ranked: boolean;
}

const ROW_HEIGHT = 34;
const RANK_AXIS_WIDTH = 84;

/** Rank order top to bottom; bar length is the metric. */
function RankedBars({ rows, ticks, kind, metric, ranked }: BarsProps) {
  const inspect = useInspect();
  return (
    <BarChart
      responsive
      accessibilityLayer={false}
      layout="vertical"
      data={rows}
      barCategoryGap={0}
      margin={{ top: 0, right: 72, bottom: 0, left: 4 }}
      style={{ width: "100%", height: rows.length * ROW_HEIGHT + 32 }}
    >
      <CartesianGrid horizontal={false} stroke={GRID} />
      <XAxis
        type="number"
        domain={[ticks[0], ticks[ticks.length - 1]]}
        ticks={ticks}
        interval={0}
        tickFormatter={(value: number) => axisTick(value, kind)}
        tick={AXIS_TICK}
        tickLine={false}
        axisLine={false}
        height={28}
      />
      <YAxis
        type="category"
        dataKey="name"
        tick={<RankTick rows={rows} ranked={ranked} />}
        tickLine={false}
        axisLine={{ stroke: GRID }}
        width={ranked ? RANK_AXIS_WIDTH : 64}
        interval={0}
      />
      <Tooltip
        cursor={{ fill: "var(--surface-2)", fillOpacity: 0.7 }}
        content={(props) => <BarTooltip {...props} metric={metric} />}
        isAnimationActive={false}
      />
      <Bar
        dataKey="value"
        barSize={16}
        shape={(props: BarShapeProps) => <BarShape {...props} rows={rows} horizontal />}
        activeBar={(props: BarShapeProps) => <BarShape {...props} rows={rows} horizontal />}
        onClick={(_, index) => openBar(inspect, rows[index])}
        animationDuration={600}
      />
    </BarChart>
  );
}

function openBar(inspect: ((index: number) => void) | null, row: BarRow | undefined) {
  if (inspect && row && row.evidence !== null) inspect(row.evidence);
}

function ColumnBars({ rows, ticks, kind, metric }: BarsProps) {
  const inspect = useInspect();
  return (
    <BarChart
      responsive
      accessibilityLayer={false}
      data={rows}
      margin={{ top: 24, right: 12, bottom: 0, left: 4 }}
      style={{ width: "100%", height: 260 }}
    >
      <CartesianGrid vertical={false} stroke={GRID} />
      <XAxis
        dataKey="name"
        tickLine={false}
        axisLine={{ stroke: GRID }}
        tick={{ fill: "var(--muted)", fontSize: 11.5 }}
        interval={0}
        height={28}
      />
      <YAxis
        domain={[ticks[0], ticks[ticks.length - 1]]}
        ticks={ticks}
        interval={0}
        tickFormatter={(value: number) => axisTick(value, kind)}
        tick={AXIS_TICK}
        tickLine={false}
        axisLine={false}
        width={56}
      />
      <Tooltip
        cursor={{ fill: "var(--surface-2)", fillOpacity: 0.7 }}
        content={(props) => <BarTooltip {...props} metric={metric} />}
        isAnimationActive={false}
      />
      <Bar
        dataKey="value"
        maxBarSize={48}
        shape={(props: BarShapeProps) => <BarShape {...props} rows={rows} />}
        activeBar={(props: BarShapeProps) => <BarShape {...props} rows={rows} />}
        onClick={(_, index) => openBar(inspect, rows[index])}
        animationDuration={600}
      />
    </BarChart>
  );
}

/**
 * One bar and its label, drawn together so a missing value (no bar) cannot
 * shift the labels of the bars after it. A derived (†) bar is drawn lighter,
 * with an outline, as a derived point is hollow.
 */
function BarShape({
  x = 0,
  y = 0,
  width = 0,
  height = 0,
  index,
  isActive,
  rows,
  horizontal = false,
}: BarShapeProps & { rows: BarRow[]; horizontal?: boolean }) {
  const row = rows[index];
  if (!row) return <g />;
  const fill = row.value < 0 ? "var(--negative)" : BAR_FILL;
  return (
    <g className={row.evidence !== null ? "cursor-pointer" : undefined}>
      {!row.missing && (
        <Rectangle
          x={x}
          y={y}
          width={width}
          height={height}
          radius={horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]}
          fill={fill}
          fillOpacity={(row.derived ? 0.45 : 1) * (isActive ? 0.8 : 1)}
          stroke={row.derived ? fill : undefined}
          strokeWidth={row.derived ? 1.5 : 0}
        />
      )}
      <BarLabel row={row} box={{ x, y, width, height }} horizontal={horizontal} />
    </g>
  );
}

/** The server's amount at the bar's end, or the muted reason a value is missing. */
function BarLabel({
  row,
  box: { x, y, width, height },
  horizontal,
}: {
  row: BarRow;
  box: { x: number; y: number; width: number; height: number };
  horizontal: boolean;
}) {
  const style = { fontVariantNumeric: "tabular-nums" } as const;
  const tone = row.missing
    ? { fill: "var(--subtle)", fontStyle: "italic" as const, fontWeight: 400 }
    : { fill: "var(--fg)", fontWeight: 500 };
  const text = row.derived && !row.missing ? `${row.label} †` : row.label;
  if (horizontal) {
    // Negative bars end at the left; their label sits beyond that end.
    const end = width < 0 ? x + width - 6 : x + width + 8;
    return (
      <text x={end} y={y + height / 2} dy="0.35em" textAnchor={width < 0 ? "end" : "start"} fontSize={11.5} style={style} {...tone}>
        {text}
      </text>
    );
  }
  const top = row.missing ? y - 8 : height < 0 ? y + 14 : y - 8;
  return (
    <text x={x + width / 2} y={top} textAnchor="middle" fontSize={11.5} style={style} {...tone}>
      {text}
    </text>
  );
}

/** "#1 AAPL": the rank in muted numerals, the ticker in full ink; the ticker alone once re-sorted. */
function RankTick({
  x,
  y,
  payload,
  rows,
  ranked,
}: {
  x?: number;
  y?: number;
  payload?: { value: string; index: number };
  rows: BarRow[];
  ranked: boolean;
}) {
  const text = payload?.value ?? "";
  const match = /^(#\d+)\s+(.*)$/.exec(text);
  const missing = rows[payload?.index ?? -1]?.missing ?? false;
  const [rank, name] = match ? [match[1], match[2]] : ["", text];
  // Fixed columns so "#1" and "#10" line their tickers up.
  return (
    <g fontSize={11.5} fontFamily="var(--font-mono)">
      {rank && ranked && (
        <text x={(x ?? 0) - RANK_AXIS_WIDTH + 4} y={y} dy="0.35em" textAnchor="start" fill="var(--subtle)">
          {rank}
        </text>
      )}
      <text
        x={(x ?? 0) - 10}
        y={y}
        dy="0.35em"
        textAnchor="end"
        fontWeight={500}
        fill={missing ? "var(--subtle)" : "var(--fg)"}
      >
        {name}
      </text>
    </g>
  );
}

function BarTooltip({
  active,
  payload,
  metric,
}: TooltipContentProps & { metric: string }) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload as BarRow;
  return (
    <TooltipBox title={row.name.replace(/^#\d+\s+/, "")}>
      <div className="flex items-baseline gap-2.5">
        {row.missing ? (
          <span className="text-[13px] font-medium text-warning">{row.label}</span>
        ) : (
          <span className="text-[13px] font-semibold tabular-nums text-fg">
            {row.amount}
            {row.derived && <span className="font-normal text-subtle"> †</span>}
          </span>
        )}
        <span className="truncate text-muted">{metric}</span>
      </div>
      {row.period && <div className="text-[11px] tabular-nums text-subtle">{row.period}</div>}
      {row.evidence !== null && <div className="mt-1 text-[11px] text-subtle">Click the bar for its source</div>}
    </TooltipBox>
  );
}
