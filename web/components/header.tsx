"use client";

import { Ellipsis, Lock, Monitor, Moon, RotateCcw, Sun } from "lucide-react";
import Link from "next/link";
import { useTheme } from "next-themes";
import { useId, useRef, type ToggleEvent } from "react";
import { cn } from "@/lib/format";
import type { RuntimeKind } from "@/lib/types";
import { ConfirmPanel, type ConfirmRequest } from "./confirm-panel";
import { LogoMark } from "./ui";
import { useHydrated } from "@/lib/browser";

const RUNTIMES: { kind: RuntimeKind; label: string }[] = [
  { kind: "recorded", label: "Recorded" },
  { kind: "live", label: "Live" },
];

export function Header({
  runtime,
  locked,
  lockedNotice,
  busy,
  restarting,
  confirm,
  onSwitchRuntime,
  onStartOver,
  onConfirm,
  onCancel,
}: {
  runtime: RuntimeKind | null;
  locked: boolean;
  lockedNotice: string;
  busy: boolean;
  /** A new conversation is being started; Start over stays available otherwise, mid-answer included. */
  restarting: boolean;
  /** The question to ask before clearing the conversation, while it is open. */
  confirm: ConfirmRequest | null;
  onSwitchRuntime: (runtime: RuntimeKind) => void;
  onStartOver: () => void;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <header className="z-30 border-b border-border bg-bg tall:sticky tall:top-0">
      <div className="mx-auto flex h-14 max-w-4xl items-center gap-3 px-4 sm:px-6 2xl:max-w-5xl min-[1920px]:max-w-6xl">
        <Link
          href="/"
          className="flex min-w-0 items-center gap-2.5 rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-primary"
          aria-label="Onfile"
        >
          <LogoMark className="size-8 shrink-0" />
          <span className="text-[17px] font-semibold leading-none tracking-[-0.02em] text-fg">Onfile</span>
          {/* One line beside the name, not a caption under it: a short name reads as the lead. */}
          <span aria-hidden className="ml-1 hidden h-4 w-px shrink-0 bg-border-strong md:block" />
          <span className="hidden truncate text-[13px] text-subtle md:block">
            Financial research from SEC filings
          </span>
        </Link>
        <PhoneMenu
          runtime={runtime}
          locked={locked}
          busy={busy || runtime === null}
          restarting={restarting}
          onSwitchRuntime={onSwitchRuntime}
          onStartOver={onStartOver}
        />
        {/* A phone keeps these in the ⋯ menu: the header stays the name and one button. */}
        <div className="ml-auto hidden items-center gap-1.5 sm:flex">
          <RuntimeSwitch
            runtime={runtime}
            locked={locked}
            lockedNotice={lockedNotice}
            disabled={busy || runtime === null}
            onChange={onSwitchRuntime}
          />
          <span aria-hidden className="mx-1 h-5 w-px bg-border" />
          <ThemeToggle />
          <button
            type="button"
            onClick={() => {
              if (!restarting) onStartOver();
            }}
            // Not `disabled`: the confirm panel hands focus back here once it starts.
            aria-disabled={restarting}
            title="Start over"
            className={cn(
              GHOST_BUTTON,
              "gap-1.5 px-2 sm:px-2.5 aria-disabled:cursor-not-allowed aria-disabled:opacity-50",
            )}
          >
            <RotateCcw className="size-3.5" aria-hidden />
            <span>Start over</span>
          </button>
        </div>
      </div>
      {confirm && <ConfirmPanel request={confirm} onConfirm={onConfirm} onCancel={onCancel} />}
    </header>
  );
}

/**
 * A phone's header controls behind "⋯": Start over, the theme, and the other
 * runtime. A native popover, so Escape and a click elsewhere close it.
 */
function PhoneMenu({
  runtime,
  locked,
  busy,
  restarting,
  onSwitchRuntime,
  onStartOver,
}: {
  runtime: RuntimeKind | null;
  locked: boolean;
  busy: boolean;
  restarting: boolean;
  onSwitchRuntime: (runtime: RuntimeKind) => void;
  onStartOver: () => void;
}) {
  const id = useId();
  const panel = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const other = RUNTIMES.find(({ kind }) => kind !== runtime);

  function place(event: ToggleEvent<HTMLDivElement>) {
    if (event.newState !== "open" || !button.current) return;
    const anchor = button.current.getBoundingClientRect();
    event.currentTarget.style.top = `${anchor.bottom + 6}px`;
    event.currentTarget.style.right = `${Math.max(12, window.innerWidth - anchor.right)}px`;
  }

  function run(action: () => void) {
    panel.current?.hidePopover();
    action();
  }

  return (
    <div className="ml-auto sm:hidden">
      <button
        ref={button}
        type="button"
        popoverTarget={id}
        aria-label="Menu"
        className={cn(GHOST_BUTTON, "w-9 border border-border")}
      >
        <Ellipsis className="size-4" aria-hidden />
      </button>
      <div
        ref={panel}
        id={id}
        popover="auto"
        role="menu"
        aria-label="Menu"
        onBeforeToggle={place}
        className="fixed inset-auto m-0 w-60 rounded-xl border border-border-strong bg-surface p-1.5 text-[13px] text-fg shadow-xl shadow-black/25"
      >
        <button
          type="button"
          role="menuitem"
          aria-disabled={restarting}
          onClick={() => run(() => !restarting && onStartOver())}
          className={MENU_ITEM}
        >
          <RotateCcw className="size-4 text-muted" aria-hidden />
          Start over
        </button>
        <PhoneTheme onDone={() => panel.current?.hidePopover()} />
        {other && runtime && (
          <button
            type="button"
            role="menuitem"
            disabled={locked || busy}
            onClick={() => run(() => onSwitchRuntime(other.kind))}
            className={cn(MENU_ITEM, "border-t border-border")}
          >
            {locked ? <Lock className="size-4 text-subtle" aria-hidden /> : <span aria-hidden className="size-4" />}
            <span className="min-w-0">
              Switch to {other.label}
              <span className="block text-[11.5px] text-subtle">
                {locked ? "Off on the public demo" : "Starts a new conversation"}
              </span>
            </span>
          </button>
        )}
      </div>
    </div>
  );
}

const MENU_ITEM =
  "flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left hover:bg-surface-2 focus-visible:bg-surface-2 " +
  "focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 aria-disabled:opacity-50";

function PhoneTheme({ onDone }: { onDone: () => void }) {
  const { current, next, setTheme } = useThemeCycle();
  const Current = current.Icon;
  return (
    <button
      type="button"
      role="menuitem"
      onClick={() => {
        setTheme(next.value);
        onDone();
      }}
      className={MENU_ITEM}
    >
      <Current className="size-4 text-muted" aria-hidden />
      Theme: {current.label}
      <span className="ml-auto text-[11.5px] text-subtle">{next.label} next</span>
    </button>
  );
}

// Utilities sit quietly beside the one bordered control, the runtime switch.
const GHOST_BUTTON =
  "inline-flex h-8 items-center justify-center rounded-lg text-xs font-medium text-muted transition-colors " +
  "hover:bg-surface-2 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary " +
  "disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-transparent disabled:hover:text-muted";

function RuntimeSwitch({
  runtime,
  locked,
  lockedNotice,
  disabled,
  onChange,
}: {
  runtime: RuntimeKind | null;
  locked: boolean;
  lockedNotice: string;
  disabled: boolean;
  onChange: (runtime: RuntimeKind) => void;
}) {
  const tooltipId = useId();
  const group = (
    <div
      role="radiogroup"
      aria-label="Runtime"
      aria-describedby={locked ? tooltipId : undefined}
      className={cn(
        "relative flex h-8 items-center rounded-lg border border-border bg-surface-2 p-0.5",
        locked && "opacity-80",
      )}
    >
      {locked && <Lock className="mx-1.5 size-3 text-subtle" aria-hidden />}
      {RUNTIMES.map(({ kind, label }) => {
        const active = kind === runtime;
        return (
          <button
            key={kind}
            type="button"
            role="radio"
            aria-checked={active}
            // The chosen runtime stays focusable, so the group can be reached and read.
            disabled={!active && (locked || disabled)}
            tabIndex={active ? 0 : -1}
            onClick={() => {
              if (!active) onChange(kind);
            }}
            onKeyDown={(event) => {
              // Arrow keys move between the two runtimes, as in any radio group.
              if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
              event.preventDefault();
              const other = RUNTIMES.find((item) => item.kind !== kind);
              if (other && !locked && !disabled) onChange(other.kind);
            }}
            className={cn(
              "inline-flex h-full items-center gap-1.5 rounded-md px-2.5 text-xs font-medium transition-colors",
              active
                ? "bg-surface text-fg shadow-sm ring-1 ring-border-strong"
                : "text-muted hover:text-fg disabled:hover:text-muted",
              !active && (locked || disabled) && "cursor-not-allowed",
              active && "cursor-default",
            )}
          >
            <span
              aria-hidden
              className={cn(
                "size-1.5 rounded-full",
                !active
                  ? "bg-subtle/50"
                  : kind === "live"
                    ? "bg-positive shadow-[0_0_0_3px] shadow-positive/20"
                    : "bg-primary shadow-[0_0_0_3px] shadow-primary/20",
              )}
            />
            {label}
          </button>
        );
      })}
    </div>
  );
  if (!locked) return group;
  return (
    <span tabIndex={0} className="group/tip relative rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-primary">
      {group}
      <span
        id={tooltipId}
        role="tooltip"
        className="pointer-events-none absolute right-0 top-[calc(100%+8px)] z-40 w-max max-w-[16rem] translate-y-1 rounded-lg border border-border-strong bg-surface px-2.5 py-1.5 text-xs text-fg opacity-0 shadow-lg shadow-black/20 transition duration-150 group-hover/tip:translate-y-0 group-hover/tip:opacity-100 group-focus-visible/tip:translate-y-0 group-focus-visible/tip:opacity-100"
      >
        <span className="flex items-center gap-1.5">
          <Lock className="size-3 text-warning" aria-hidden />
          {lockedNotice}
        </span>
      </span>
    </span>
  );
}

const THEMES = [
  { value: "system", label: "System", Icon: Monitor },
  { value: "light", label: "Light", Icon: Sun },
  { value: "dark", label: "Dark", Icon: Moon },
] as const;

/** The theme shown, the one after it in System → Light → Dark, and how to switch. */
function useThemeCycle() {
  const { theme, setTheme } = useTheme();
  // next-themes only knows the stored theme after hydration; the server cannot
  // know it either, so its default is shown until then.
  const mounted = useHydrated();
  const shown = mounted ? (theme ?? "dark") : "dark";
  const index = Math.max(0, THEMES.findIndex(({ value }) => value === shown));
  return { mounted, current: THEMES[index], next: THEMES[(index + 1) % THEMES.length], setTheme };
}

/** One button that steps System → Light → Dark; its icon shows the current choice. */
function ThemeToggle() {
  const { mounted, current, next, setTheme } = useThemeCycle();
  const label = `Theme: ${current.label}. Switch to ${next.label.toLowerCase()}`;
  return (
    <button
      type="button"
      onClick={() => setTheme(next.value)}
      aria-label={label}
      title={label}
      className={cn(GHOST_BUTTON, "w-8", !mounted && "invisible")}
    >
      <current.Icon className="size-4" aria-hidden />
    </button>
  );
}
