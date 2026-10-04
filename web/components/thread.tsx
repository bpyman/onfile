"use client";

import { Loader2, RotateCcw, RotateCw } from "lucide-react";
import { useCallback, useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { clarifyChoices, shownMessage } from "@/lib/clarify";
import { progressLabel, type TurnState } from "@/lib/turn-state";
import type { Presentation, RuntimeKind, Turn } from "@/lib/types";
import { Answer } from "./answer";
import { AnswerBoundary } from "./answer-boundary";
import { AnswerScope } from "./answer-scope";
import { cn } from "@/lib/format";
import { Button, Callout, LogoMark } from "./ui";

/** The conversation: finished turns, then the running or failed one. */
export function Thread({
  turns,
  turn,
  runtime = null,
  demo = null,
  full = false,
  onRetry,
  onAsk,
  onStartOver,
  onTryRecorded,
}: {
  turns: Turn[];
  turn: TurnState;
  /** The thread's runtime, for an answer's shared link. */
  runtime?: RuntimeKind | null;
  /** The running story's recorded answer, shown while the service wakes. */
  demo?: Presentation | null;
  /** The conversation has used every turn: nothing can be asked on it. */
  full?: boolean;
  onRetry: (message: string) => void;
  /** Sends a clarify candidate's slug as the next analyst message. */
  onAsk: (message: string) => void;
  onStartOver: () => void;
  /** Offered when a live answer is slow; absent where Recorded is no option. */
  onTryRecorded?: (message: string) => void;
}) {
  const running = turn.status === "running";
  // The window recreates its send function as progress arrives. Answers need one
  // stable event callback so that those parent renders do not invalidate memoised props.
  const onAskRef = useRef(onAsk);
  useEffect(() => {
    onAskRef.current = onAsk;
  }, [onAsk]);
  const ask = useCallback((message: string) => onAskRef.current(message), []);
  return (
    // Turns sit well apart, a rule between them, so each answer reads as its own.
    <ol
      className="space-y-14 pt-8 sm:space-y-16 sm:pt-10 [&>li+li]:border-t [&>li+li]:border-border/70 [&>li+li]:pt-12 sm:[&>li+li]:pt-14"
      aria-label="Conversation"
    >
      {turns.map((item, index) => (
        <li
          key={item.index}
          data-turn={index}
          className="scroll-mt-4 tall:scroll-mt-20 sm:tall:scroll-mt-40"
        >
          <AnswerScope value={index > 0 ? `answer ${index + 1}` : ""}>
            <Exchange message={shownMessage(item, turns[index - 1])} sent={item.message} heading={`Answer ${index + 1}`}>
              <AnswerBoundary>
                <ThreadAnswer
                  item={item}
                  previous={turns[index - 1]}
                  next={turns[index + 1]}
                  messages={turns}
                  index={index}
                  runtime={runtime}
                  suggest={index === turns.length - 1 && turn.status === "idle" && !full}
                  clarifyLive={item.clarify_enabled && !running && !full}
                  onAsk={ask}
                />
              </AnswerBoundary>
            </Exchange>
          </AnswerScope>
        </li>
      ))}
      {turn.status === "running" && (
        <li data-turn="pending" className="scroll-mt-4 tall:scroll-mt-20 sm:tall:scroll-mt-40">
          <Exchange message={shownMessage(turn, turns.at(-1))} sent={turn.message} working>
            <Working
              state={turn}
              slim={demo !== null}
              onTryRecorded={onTryRecorded && turn.message ? () => onTryRecorded(turn.message) : undefined}
            />
            {demo && (
              <div className="mt-4">
                <AnswerBoundary>
                  <Answer question={turn.message} presentation={demo} demo />
                </AnswerBoundary>
              </div>
            )}
          </Exchange>
        </li>
      )}
      {turn.status === "failed" && (
        <li data-turn="pending" className="scroll-mt-4 tall:scroll-mt-20 sm:tall:scroll-mt-40">
          <Exchange message={shownMessage(turn, turns.at(-1))} sent={turn.message}>
            <Callout kind="error">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <span>{turn.error}</span>
                {/* A full conversation refuses every retry; only a new one can answer. */}
                {full ? (
                  <Button size="sm" variant="outline" onClick={onStartOver}>
                    <RotateCcw className="size-3.5" aria-hidden />
                    Start over
                  </Button>
                ) : (
                  <Button size="sm" variant="outline" onClick={() => onRetry(turn.message)}>
                    <RotateCw className="size-3.5" aria-hidden />
                    Try again
                  </Button>
                )}
              </div>
            </Callout>
          </Exchange>
        </li>
      )}
    </ol>
  );
}

/** Stabilises the two aggregate props that would otherwise defeat Answer's memo. */
function ThreadAnswer({
  item,
  previous,
  next,
  messages,
  index,
  runtime,
  suggest,
  clarifyLive,
  onAsk,
}: {
  item: Turn;
  previous?: Turn;
  next?: Turn;
  messages: Turn[];
  index: number;
  runtime: RuntimeKind | null;
  suggest: boolean;
  clarifyLive: boolean;
  onAsk: (message: string) => void;
}) {
  const conversation = useMemo(
    () => messages.slice(0, index + 1).map((sent) => sent.message),
    [messages, index],
  );
  const clarify = useMemo(
    () => ({
      choices: clarifyChoices(item, next),
      live: clarifyLive,
      onChoose: onAsk,
    }),
    [item, next, clarifyLive, onAsk],
  );
  return (
    <Answer
      question={shownMessage(item, previous)}
      conversation={conversation}
      presentation={item.presentation}
      runtime={runtime}
      onSuggest={suggest ? onAsk : undefined}
      clarify={clarify}
    />
  );
}

function Exchange({
  message,
  sent,
  working = false,
  heading,
  children,
}: {
  message: string;
  /** The message as sent, when the thread shows it differently (a clarify slug). */
  sent?: string;
  working?: boolean;
  /** A heading for screen readers to jump between answers by. */
  heading?: string;
  children: ReactNode;
}) {
  return (
    <div className="animate-fade-up">
      {/* No bubble for a turn reattached after a reload: its message is not known yet. */}
      {message && (
        <div className="flex justify-end">
          <Question message={message} sent={sent} />
        </div>
      )}
      {heading && <h2 className="sr-only">{heading}</h2>}
      <div className={message ? "mt-5 flex gap-3" : "flex gap-3"}>
        <div className="relative hidden shrink-0 sm:block">
          <LogoMark className="size-7" />
          {working && (
            <span aria-hidden className="absolute -right-0.5 -top-0.5 flex size-2.5">
              <span className="absolute inset-0 animate-ping rounded-full bg-primary/60" />
              <span className="relative size-2.5 rounded-full bg-primary ring-2 ring-bg" />
            </span>
          )}
        </div>
        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </div>
  );
}

/** How long a live answer runs before Recorded is offered instead. */
const SLOW_AFTER_SECONDS = 15;

function Working({
  state,
  slim = false,
  onTryRecorded,
}: {
  state: Extract<TurnState, { status: "running" }>;
  /** A recorded answer shows below: the status and progress only, no placeholder. */
  slim?: boolean;
  onTryRecorded?: () => void;
}) {
  const { progress, waking } = state;
  const seconds = useElapsedSeconds();
  const fraction =
    progress && progress.total > 0 ? Math.min(1, progress.done / progress.total) : null;
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface">
      <div className="px-4 py-3.5">
        <div className="flex items-center gap-2 text-[13px] font-medium text-fg" role="status">
          <Loader2 className="size-4 animate-spin text-primary" aria-hidden />
          {progressLabel(state)}
          {waking && (
            // Ticks every second: kept out of the live region so it is not read out each time.
            <span className="num ml-auto text-[11.5px] font-normal text-subtle" aria-hidden>
              {seconds} s
            </span>
          )}
        </div>
        {(waking || slim) && (
          <p className="mt-1 pl-6 text-xs text-muted">
            The hosted service sleeps when idle and can take about a minute to wake.
            {slim && " Meanwhile, here is this story's recorded answer; the fresh one replaces it."}
          </p>
        )}
        {onTryRecorded && seconds >= SLOW_AFTER_SECONDS && (
          <p className="mt-1.5 pl-6 text-xs text-muted">
            Taking a while?{" "}
            <button
              type="button"
              onClick={onTryRecorded}
              className="rounded font-medium text-primary underline underline-offset-4"
            >
              Try Recorded instead
            </button>{" "}
            — captured filings answer at once.
          </p>
        )}
      </div>
      <div className="h-0.5 bg-surface-3" aria-hidden>
        {fraction === null ? (
          <div className="h-full w-1/3 animate-[indeterminate_1.4s_ease-in-out_infinite] bg-gradient-to-r from-transparent via-primary to-transparent" />
        ) : (
          <div
            className="h-full bg-primary transition-[width] duration-300"
            style={{ width: `${Math.max(fraction * 100, 4)}%` }}
          />
        )}
      </div>
      {!slim && (
        <div className="space-y-3 px-4 py-4" aria-hidden>
          <div className="shimmer animate-shimmer h-3 w-24 rounded" />
          <div className="shimmer animate-shimmer h-9 w-48 rounded-md" />
          <div className="shimmer animate-shimmer h-3 w-64 max-w-full rounded" />
        </div>
      )}
    </div>
  );
}

/** Whole seconds since the component appeared. */
function useElapsedSeconds(): number {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const start = performance.now();
    const timer = window.setInterval(() => setSeconds(Math.floor((performance.now() - start) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return seconds;
}

// A question longer than this, or with more lines, starts folded to eight lines.
const LONG_QUESTION_CHARS = 400;
const LONG_QUESTION_LINES = 8;

/** The analyst's question; a pasted wall of text folds, with a button to unfold it. */
function Question({ message, sent }: { message: string; sent?: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const long = message.length > LONG_QUESTION_CHARS || message.split("\n").length > LONG_QUESTION_LINES;
  return (
    <div className="flex max-w-[88%] flex-col items-end gap-1 sm:max-w-[75%]">
      <p
        id={id}
        title={sent && sent !== message ? `Sent as ${sent}` : undefined}
        className="whitespace-pre-wrap break-words rounded-2xl [overflow-wrap:anywhere] rounded-br-md border border-border bg-surface-2 px-4 py-2.5 text-[15px] leading-relaxed text-fg"
      >
        {/* Clamped inside the padding, so no part of a ninth line shows below it. */}
        <span className={cn("block", long && !open && "line-clamp-8")}>{message}</span>
      </p>
      {long && (
        <button
          type="button"
          aria-expanded={open}
          aria-controls={id}
          onClick={() => setOpen((shown) => !shown)}
          className="rounded px-1 text-[12px] font-medium text-muted underline-offset-4 hover:text-fg hover:underline"
        >
          {open ? "Show less" : "Show more"}
        </button>
      )}
    </div>
  );
}
