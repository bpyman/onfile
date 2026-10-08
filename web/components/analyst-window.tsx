"use client";

import { X } from "lucide-react";
import { useEffect, useMemo, useReducer, useRef, useState, useSyncExternalStore } from "react";
import {
  ApiError,
  createThread,
  deleteThread,
  getMeta,
  getThread,
  pingHealth,
  runTurn,
} from "@/lib/api";
import {
  THREAD_STORAGE_KEY,
  ThreadMovedError,
  askOnThread,
  browserStore,
  isCurrentThread,
  resumeThread,
  startOverIfLocked,
  startThread,
  waitForTurn,
  whenFree,
  type KeyValueStore,
  type ThreadApi,
} from "@/lib/browser-thread";
import { loadDemoAnswers } from "@/lib/demo-answers";
import { parseShareLink } from "@/lib/share-link";
import { shortcutFor } from "@/lib/shortcuts";
import { IDLE, WAKE_AFTER_MS, turnReducer } from "@/lib/turn-state";
import type { Meta, Presentation, RuntimeKind, ThreadView } from "@/lib/types";
import { Composer, type ComposerHandle } from "./composer";
import type { ConfirmRequest } from "./confirm-panel";
import { Header } from "./header";
import { Landing } from "./landing";
import { StatusLine } from "./status-line";
import { Thread } from "./thread";
import { Callout } from "./ui";
import { subscribeNothing } from "@/lib/browser";

const threadApi: ThreadApi = { createThread, getThread, deleteThread };
const UNREACHABLE = "The analysis service is unreachable. Please try again shortly.";
const OTHER_TAB_NOTICE = "This conversation changed in another tab, so this one follows it.";
const MOVED_NOTICE = `${OTHER_TAB_NOTICE} Your question is back in the box to send again.`;
const START_OVER_CONFIRM: ConfirmRequest = {
  title: "Start over?",
  body: "This clears the current conversation.",
  action: "Clear conversation",
};
const SWITCH_CONFIRM: ConfirmRequest = {
  title: "Switch runtime?",
  body: "This starts a new conversation and clears the current one.",
  action: "Switch runtime",
};
const PLACEHOLDER = "Ask about a company's filings…";
const UNFINISHED = "Your last question could not be completed. Please ask it again.";
const ANSWER_READY = "Answer ready.";
/** The composer's limit until meta brings the server's `max_message_chars`. */
const MAX_MESSAGE_CHARS_BEFORE_META = 2000;

type Notice = { kind: "info" | "error"; text: string };

function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return UNREACHABLE;
}

/** The thread as the server has it, or null when this browser has moved on to another since. */
async function loadIfCurrent(store: KeyValueStore, threadId: string): Promise<ThreadView | null> {
  const latest = await getThread(threadId);
  return isCurrentThread(store, threadId) ? latest : null;
}

/** The audience window: one thread per browser, bound to one runtime (ADR 0006). */
export function AnalystWindow() {
  const store = useMemo(() => browserStore(), []);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [metaError, setMetaError] = useState<string | null>(null);
  const [metaWaking, setMetaWaking] = useState(false);
  const [metaAttempt, setMetaAttempt] = useState(0);
  const [view, setView] = useState<ThreadView | null>(null);
  const [chosenRuntime, setChosenRuntime] = useState<RuntimeKind | null>(null);
  const [booted, setBooted] = useState(false);
  const [resumeFailed, setResumeFailed] = useState(false);
  const [resumeAttempt, setResumeAttempt] = useState(0);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [turn, dispatch] = useReducer(turnReducer, IDLE);
  const [switching, setSwitching] = useState(false);
  // Read out once an answer lands, for a screen reader left on the question box.
  const [announcement, setAnnouncement] = useState("");
  // Start over or a runtime switch waiting on the analyst's answer.
  const [confirming, setConfirming] = useState<{ next: RuntimeKind | null; request: ConfirmRequest } | null>(null);
  const inFlight = useRef(false);
  // The running answer, or the reload's wait for one; Start over aborts it.
  const work = useRef<AbortController | null>(null);
  const composer = useRef<ComposerHandle | null>(null);
  const shownTurns = useRef(0);
  // The API has answered this visit: a slow turn now is work, not a wake-up.
  const awake = useRef(false);
  // A guided story's recorded answer, shown while a sleeping API wakes.
  const [demo, setDemo] = useState<{ question: string; presentation: Presentation } | null>(null);
  // A shared link's question is asked once per load, whatever re-renders follow.
  const shared = useRef<ReturnType<typeof parseShareLink> | undefined>(undefined);

  // Read after hydration only, so the server render and the first client render agree.
  const storedThreadId = useSyncExternalStore(
    subscribeNothing,
    () => store.getItem(THREAD_STORAGE_KEY),
    () => null,
  );

  const locked = meta?.runtime.locked ?? false;
  // Until the saved thread is back, a question or Start over would start another
  // thread under it, and the restored one would then replace it on screen.
  const resuming = !booted && storedThreadId !== null;
  const runtime = view?.runtime ?? (resuming || resumeFailed ? null : chosenRuntime ?? meta?.runtime.default ?? null);
  const busy = turn.status === "running" || switching || resuming;
  const hasThread = (view?.turns.length ?? 0) > 0 || turn.status !== "idle";
  const full = view ? view.turn_count >= view.max_turns : false;

  // Wake on visit, then resume the stored thread. A reload mid-turn finds the
  // turn still in flight: show it running and poll until the answer lands.
  useEffect(() => {
    void pingHealth().then((ok) => {
      if (ok) awake.current = true;
    });
    const aborted = new AbortController();
    const { signal } = aborted;
    // Start over aborts the reload too, so the saved thread cannot come back over the new one.
    work.current = aborted;

    async function reattach(resumed: ThreadView) {
      inFlight.current = true;
      dispatch({ type: "reattach" });
      try {
        const finished = await waitForTurn(getThread, resumed.thread_id, { signal });
        setView(finished);
        dispatch({ type: "event", event: { event: "thread", data: finished } });
        if (finished.turns.length === resumed.turns.length) {
          setNotice({ kind: "error", text: UNFINISHED });
        } else {
          setAnnouncement(ANSWER_READY);
        }
      } catch (error) {
        if (signal.aborted) return;
        dispatch({ type: "reset" });
        setNotice({ kind: "error", text: errorText(error) });
      } finally {
        if (work.current === aborted) {
          work.current = null;
          inFlight.current = false;
        }
      }
    }

    resumeThread(threadApi, store)
      .then((resumed) => {
        // `null`: the analyst started another thread while this one loaded.
        if (signal.aborted || resumed === null) return;
        setResumeFailed(false);
        setView(resumed.view);
        setNotice(resumed.notice ? { kind: "info", text: resumed.notice } : null);
        if (resumed.view?.turn_in_flight) void reattach(resumed.view);
      })
      .catch((error: unknown) => {
        if (!signal.aborted) {
          setResumeFailed(true);
          setNotice({
            kind: "error",
            text: `Your conversation couldn't be loaded. ${errorText(error)}`,
          });
        }
      })
      .finally(() => {
        if (!signal.aborted) setBooted(true);
      });
    return () => aborted.abort();
  }, [store, resumeAttempt]);

  // A shared link (/?q=…&q=…&rt=…) asks its questions, in order, in a new
  // conversation once the saved one is back; the address is cleaned first, so a
  // reload asks nothing.
  useEffect(() => {
    if (shared.current === undefined) {
      shared.current = parseShareLink(window.location.search, MAX_MESSAGE_CHARS_BEFORE_META);
      if (window.location.search) window.history.replaceState(window.history.state, "", window.location.pathname);
    }
    const link = shared.current;
    if (!link || resuming) return;
    shared.current = null;
    void startOver(link.runtime, { keepPrevious: true }).then(async (started) => {
      let current: ThreadView | null = started ?? null;
      for (const question of link.questions) {
        if (!current) return;
        // Each follow-up is asked of the thread the previous answer left.
        current = await ask(question, current);
      }
    });
    // startOver and ask read the latest state when they run; only the resume gates this.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resuming]);

  // "/" jumps to the question box from anywhere but another field.
  useEffect(() => {
    const jump = (event: KeyboardEvent) => {
      const target = event.target instanceof HTMLElement ? event.target : null;
      const shortcut = shortcutFor({
        key: event.key,
        targetTag: target?.tagName ?? "",
        editable: target?.isContentEditable ?? false,
        modifier: event.ctrlKey || event.metaKey || event.altKey,
      });
      if (shortcut !== "focus-composer" || event.defaultPrevented) return;
      event.preventDefault();
      composer.current?.focus();
    };
    window.addEventListener("keydown", jump);
    return () => window.removeEventListener("keydown", jump);
  }, []);

  // A live thread on a deployment locked to the recorded runtime would refuse
  // every turn: Start over on the recorded runtime and say why.
  useEffect(() => {
    if (!locked || view?.runtime !== "live" || inFlight.current) return;
    inFlight.current = true;
    startOverIfLocked(threadApi, store, view, locked)
      .then((started) => {
        if (!started) return;
        dispatch({ type: "reset" });
        showThread(started.view, started.notice);
      })
      .catch((error: unknown) => {
        setView(null);
        setNotice({ kind: "error", text: errorText(error) });
      })
      .finally(() => {
        inFlight.current = false;
      });
  }, [locked, view, store]);

  // Storefront copy, and the snapshot banner for the runtime in use.
  useEffect(() => {
    let cancelled = false;
    const waking = window.setTimeout(() => setMetaWaking(true), WAKE_AFTER_MS);
    getMeta(runtime ?? undefined)
      .then((loaded) => {
        awake.current = true;
        if (cancelled) return;
        setMeta(loaded);
        setMetaError(null);
      })
      .catch((error: unknown) => {
        if (!cancelled) setMetaError(errorText(error));
      })
      .finally(() => {
        window.clearTimeout(waking);
        if (!cancelled) setMetaWaking(false);
      });
    return () => {
      cancelled = true;
      window.clearTimeout(waking);
    };
  }, [runtime, metaAttempt]);

  // Bring the newest exchange into view: the running turn, or the answer that just landed.
  const turnCount = view?.turns.length ?? 0;
  useEffect(() => {
    const target =
      turn.status !== "idle"
        ? document.querySelector('[data-turn="pending"]')
        : turnCount > shownTurns.current
          ? document.querySelector(`[data-turn="${turnCount - 1}"]`)
          : null;
    shownTurns.current = turnCount;
    if (!target) return;
    target.scrollIntoView({
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
      block: "start",
    });
    // Chrome starts Tab from what is in view; with nothing focused (a resumed
    // thread), start it from the top, so the first Tab reaches the skip link.
    if (document.activeElement === document.body) {
      document.body.tabIndex = -1;
      document.body.focus({ preventScroll: true });
      document.body.removeAttribute("tabindex");
    }
  }, [turn.status, turnCount]);

  // Another tab started over or switched runtime: follow it rather than keep
  // showing a thread this browser no longer holds.
  useEffect(() => {
    const follow = (event: StorageEvent) => {
      if (event.key !== THREAD_STORAGE_KEY || inFlight.current) return;
      if (event.newValue === (view?.thread_id ?? null)) return;
      dispatch({ type: "reset" });
      if (!event.newValue) {
        showThread(null, OTHER_TAB_NOTICE);
        return;
      }
      loadIfCurrent(store, event.newValue)
        .then((latest) => {
          if (latest) showThread(latest, OTHER_TAB_NOTICE);
        })
        .catch(() => undefined);
    };
    window.addEventListener("storage", follow);
    return () => window.removeEventListener("storage", follow);
  }, [store, view?.thread_id]);

  // Escape dismisses a notice, as its × does; a failed resume keeps its buttons,
  // and an open confirm panel takes Escape for itself (it marks the event).
  useEffect(() => {
    if (!notice || resumeFailed) return;
    const dismiss = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !event.defaultPrevented) setNotice(null);
    };
    window.addEventListener("keydown", dismiss);
    return () => window.removeEventListener("keydown", dismiss);
  }, [notice, resumeFailed]);

  /** Shows another thread (or none) from its top, with the notice that explains the change. */
  function showThread(next: ThreadView | null, notice?: string | null) {
    shownTurns.current = 0;
    setView(next);
    if (notice) setNotice({ kind: "info", text: notice });
  }

  /** Loads the saved thread again after a failed resume. */
  function retryResume() {
    setBooted(false);
    setResumeAttempt((attempt) => attempt + 1);
  }

  /** Takes a question if the window can ask it now; false leaves it in the box. */
  function send(text: string): boolean {
    const message = text.trim();
    if (!message || inFlight.current || resuming || resumeFailed || full) return false;
    void ask(message);
    return true;
  }

  /** Asks `message` on the thread on screen, or on `fresh` when Start over just made one. */
  async function ask(message: string, fresh?: ThreadView): Promise<ThreadView | null> {
    inFlight.current = true;
    const controller = new AbortController();
    work.current = controller;
    dispatch({ type: "send", message });
    setNotice(null);
    setAnnouncement("");
    const waking = window.setTimeout(() => {
      if (!awake.current) dispatch({ type: "wake" });
    }, WAKE_AFTER_MS);
    const shown = fresh ?? view;
    let threadId = shown?.thread_id;
    let stale = false;
    let answered = false;
    let moved: string | null = null;
    let latest: ThreadView | null = null;
    try {
      if (!threadId) {
        // Before the analyst picks a runtime, the server applies its deployment default.
        const started = await startThread(threadApi, store, chosenRuntime ?? undefined);
        if (controller.signal.aborted) return null;
        setView(started.view);
        threadId = started.view.thread_id;
        if (started.notice) setNotice({ kind: "info", text: started.notice });
      }
      const asked = askOnThread(
        threadApi,
        store,
        (id, text) =>
          whenFree(() => runTurn(id, text, controller.signal), { onBusy: () => dispatch({ type: "queued" }) }),
        threadId,
        message,
        shown?.runtime ?? chosenRuntime ?? undefined,
        (started) => {
          // The server lost the thread while the window sat open.
          showThread(started.view, started.notice);
          threadId = started.view.thread_id;
        },
      );
      for await (const event of asked) {
        if (controller.signal.aborted) break;
        awake.current = true;
        if (event.event === "thread") {
          setView(event.data);
          latest = event.data;
          answered = true;
        }
        if (event.event === "error") stale = true;
        dispatch({ type: "event", event });
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        if (error instanceof ThreadMovedError) {
          moved = error.threadId;
          dispatch({ type: "reset" });
        } else {
          stale = true;
          dispatch({ type: "fail", error: errorText(error) });
        }
      }
    } finally {
      window.clearTimeout(waking);
      // Start over took the window over: leave its flags alone.
      if (work.current === controller) {
        work.current = null;
        inFlight.current = false;
      }
    }
    if (controller.signal.aborted) return null;
    if (answered) setAnnouncement(ANSWER_READY);
    if (moved) {
      // Another tab's Start over replaced this thread: show that one, and hand the question back.
      loadIfCurrent(store, moved)
        .then((latest) => {
          if (!latest) return;
          showThread(latest, MOVED_NOTICE);
          composer.current?.fill(message);
        })
        .catch((error: unknown) => setNotice({ kind: "error", text: errorText(error) }));
      return null;
    }
    if (stale && threadId) refresh(threadId);
    return stale ? null : latest;
  }

  /**
   * A failed or dropped turn can still have changed the thread (its turn and
   * budget counts); redraw from the server rather than keep the stale view,
   * unless the analyst has started over since.
   */
  function refresh(threadId: string) {
    loadIfCurrent(store, threadId)
      .then((latest) => {
        if (latest) setView(latest);
      })
      .catch(() => undefined);
  }

  /**
   * Start over on `next`: the same runtime, or the other one when the switch
   * flips. Asked first, in the page, when there is a conversation to lose.
   */
  function restart(next: RuntimeKind | null) {
    if (switching) return;
    if (hasThread || resuming || resumeFailed) {
      const changesRuntime = next !== null && next !== runtime;
      setConfirming({ next, request: changesRuntime ? SWITCH_CONFIRM : START_OVER_CONFIRM });
      return;
    }
    void startOver(next);
  }

  /**
   * Drops a running answer or a reload still loading, then opens a new thread.
   * `keepPrevious` leaves the old thread to expire rather than deleting it (a
   * saved conversation that could not be loaded). The new thread is made before
   * anything is cleared, so a refusal keeps the conversation on screen. Returns
   * the new thread, or null when none could start.
   */
  async function startOver(
    next: RuntimeKind | null,
    { keepPrevious = false }: { keepPrevious?: boolean } = {},
  ): Promise<ThreadView | null> {
    setConfirming(null);
    const wasResuming = resuming;
    const hadResumeFailed = resumeFailed;
    const dropped = turn.status === "running" ? view?.thread_id : undefined;
    work.current?.abort();
    work.current = null;
    inFlight.current = true;
    setSwitching(true);
    // A saved thread still loading is dropped: `resumeThread` sees the new id and ignores it.
    setBooted(true);
    setResumeFailed(false);
    setNotice(null);
    dispatch({ type: "reset" });
    try {
      const previous = keepPrevious ? null : (view?.thread_id ?? store.getItem(THREAD_STORAGE_KEY));
      const started = await startThread(threadApi, store, next ?? undefined, previous);
      setChosenRuntime(next);
      showThread(started.view, started.notice);
      composer.current?.clear();
      window.scrollTo({ top: 0 });
      return started.view;
    } catch (error) {
      // Nothing was cleared: keep the conversation and say why no new one started.
      setNotice({ kind: "error", text: errorText(error) });
      if (hadResumeFailed) setResumeFailed(true);
      else if (wasResuming) retryResume();
      if (dropped) refresh(dropped);
      return null;
    } finally {
      inFlight.current = false;
      setSwitching(false);
    }
  }

  /** A slow live answer: ask the same question on a new recorded thread. */
  async function tryRecorded(message: string) {
    const started = await startOver("recorded");
    if (started) void ask(message, started);
  }

  /**
   * A guided story: asked as any question, and while the API is still waking,
   * its recorded answer shows at once until the real one lands.
   */
  function askStory(question: string) {
    if (!send(question) || awake.current) return;
    void loadDemoAnswers()
      .then((answers) => {
        const presentation = answers.get(question);
        if (presentation && !awake.current) setDemo({ question, presentation });
      })
      .catch(() => undefined);
  }

  function draftQuestion(question: string) {
    composer.current?.fill(question);
  }

  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#composer"
        onClick={(event) => {
          event.preventDefault();
          composer.current?.focus();
        }}
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-3 focus:z-50 focus:rounded-lg focus:border focus:border-border-strong focus:bg-surface focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:text-fg focus:shadow-lg"
      >
        Skip to the question box
      </a>
      <Header
        runtime={runtime}
        locked={locked}
        lockedNotice={meta?.runtime_copy.locked ?? ""}
        busy={busy}
        restarting={switching}
        confirm={confirming?.request ?? null}
        onSwitchRuntime={restart}
        onStartOver={() => restart(runtime)}
        onConfirm={() => confirming && void startOver(confirming.next)}
        onCancel={() => setConfirming(null)}
      />
      <StatusLine
        runtime={runtime}
        runtimeBanner={meta && runtime ? meta.runtime_copy[runtime] : metaError || resumeFailed ? "" : null}
        guide={meta?.runtime_guide ?? null}
        snapshot={meta?.snapshot ?? null}
        chips={view?.spec_chips ?? []}
        edits={view?.spec_chip_edits ?? []}
        actions={view?.quick_actions ?? null}
        editable={!busy && !full && !resumeFailed}
        onEdit={send}
        onDraft={draftQuestion}
        turns={view && view.turn_count > 0 ? { count: view.turn_count, max: view.max_turns } : null}
      />
      <main className="mx-auto w-full max-w-4xl flex-1 px-4 pb-44 short:pb-24 sm:px-6 2xl:max-w-5xl min-[1920px]:max-w-6xl">
        {notice && (
          <Callout kind={notice.kind} className="mt-6 animate-fade-up">
            <div className="flex items-start justify-between gap-3">
              <span>{notice.text}</span>
              {resumeFailed ? (
                <span className="flex shrink-0 flex-wrap justify-end gap-x-3 gap-y-1">
                  <button
                    type="button"
                    disabled={resuming}
                    onClick={retryResume}
                    className="rounded text-sm font-medium underline underline-offset-4 disabled:opacity-50"
                  >
                    Try again
                  </button>
                  {/* The saved thread is left to expire, not deleted unseen. */}
                  <button
                    type="button"
                    disabled={switching}
                    onClick={() => void startOver(null, { keepPrevious: true })}
                    className="rounded text-sm font-medium underline underline-offset-4 disabled:opacity-50"
                  >
                    Start a new conversation
                  </button>
                </span>
              ) : (
                <button
                  type="button"
                  onClick={() => setNotice(null)}
                  aria-label="Dismiss"
                  className="-mr-1 rounded p-0.5 text-subtle hover:text-fg"
                >
                  <X className="size-3.5" aria-hidden />
                </button>
              )}
            </div>
          </Callout>
        )}
        {resuming ? (
          <ResumeSkeleton />
        ) : resumeFailed ? null : hasThread ? (
          <>
            <h1 className="sr-only">Your conversation</h1>
            <Thread
              turns={view?.turns ?? []}
              turn={turn}
              runtime={runtime}
              demo={
                demo && turn.status === "running" && turn.message === demo.question
                  ? demo.presentation
                  : null
              }
              full={full}
              onRetry={send}
              onAsk={send}
              onStartOver={() => restart(runtime)}
              onTryRecorded={
                runtime === "live" && !locked && (view?.turns.length ?? 0) === 0
                  ? (message) => void tryRecorded(message)
                  : undefined
              }
            />
          </>
        ) : (
          <Landing
            meta={meta}
            waking={metaWaking}
            error={metaError}
            disabled={busy}
            onAsk={send}
            onStory={askStory}
            onDraft={draftQuestion}
            onRetry={() => setMetaAttempt((attempt) => attempt + 1)}
          />
        )}
        <div className="sr-only" role="status" aria-live="polite">
          {announcement}
        </div>
        <Composer
          ref={composer}
          onSend={send}
          busy={busy || resumeFailed}
          busyLabel={resuming ? "Loading your thread" : resumeFailed ? "Resume your thread to continue" : "Analysis running"}
          placeholder={PLACEHOLDER}
          maxChars={meta?.max_message_chars ?? MAX_MESSAGE_CHARS_BEFORE_META}
          turnsLeft={view ? view.max_turns - view.turn_count : null}
          lastQuestion={view?.turns.at(-1)?.message ?? ""}
        />
      </main>
    </div>
  );
}

function ResumeSkeleton() {
  return (
    <div className="space-y-5 pt-10" aria-busy="true" aria-label="Loading your thread">
      <div className="flex justify-end">
        <div className="shimmer animate-shimmer h-10 w-2/3 max-w-md rounded-2xl" />
      </div>
      <div className="shimmer animate-shimmer h-56 w-full rounded-2xl" />
      <div className="shimmer animate-shimmer h-32 w-full rounded-xl" />
    </div>
  );
}
