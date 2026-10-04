import { ArrowUpRight, Info, OctagonAlert, TriangleAlert } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";
import { cn, safeHref } from "@/lib/format";

type ButtonVariant = "primary" | "secondary" | "ghost" | "outline";

const BUTTON: Record<ButtonVariant, string> = {
  primary:
    "bg-primary-solid text-primary-fg shadow-sm shadow-primary/20 hover:brightness-110 disabled:opacity-40",
  secondary: "bg-surface-2 text-fg hover:bg-surface-3 disabled:opacity-50",
  outline:
    "border border-border bg-surface text-fg hover:border-border-strong hover:bg-surface-2 disabled:opacity-50",
  ghost: "text-muted hover:bg-surface-2 hover:text-fg disabled:opacity-50",
};

export function Button({
  variant = "secondary",
  size = "md",
  className,
  ...props
}: ComponentProps<"button"> & { variant?: ButtonVariant; size?: "sm" | "md" | "icon" }) {
  return (
    <button
      type="button"
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-[background,border,filter,color] disabled:cursor-not-allowed",
        size === "sm" && "h-7 px-2.5 text-xs",
        size === "md" && "h-9 px-3.5 text-sm",
        size === "icon" && "size-9",
        BUTTON[variant],
        className,
      )}
      {...props}
    />
  );
}

export function ExternalLink({
  href,
  children,
  className,
}: {
  href: string;
  children: ReactNode;
  className?: string;
}) {
  if (!safeHref(href)) return <span className={className}>{children}</span>;
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      className={cn(
        "inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline",
        className,
      )}
    >
      {children}
      <ArrowUpRight className="size-3.5 shrink-0" aria-hidden />
    </a>
  );
}

export function FilingButton({
  href,
  label = "Open filing",
  emphasis = false,
}: {
  href: string;
  label?: string;
  /** The primary action of a card, tinted in the primary colour. */
  emphasis?: boolean;
}) {
  if (!safeHref(href)) return null;
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      className={cn(
        "inline-flex h-8 items-center gap-1.5 whitespace-nowrap rounded-lg border px-3 text-xs font-medium transition-colors",
        emphasis
          ? "border-primary/30 bg-primary-soft text-primary hover:border-primary/60"
          : "border-border bg-surface text-fg hover:border-primary/50 hover:text-primary",
      )}
    >
      {label}
      <ArrowUpRight className="size-3.5" aria-hidden />
    </a>
  );
}

const TONES = {
  neutral: "border-border bg-surface-2 text-muted",
  primary: "border-primary/25 bg-primary-soft text-primary",
  positive: "border-positive/25 bg-positive-soft text-positive",
  negative: "border-negative/25 bg-negative-soft text-negative",
  warning: "border-warning/25 bg-warning-soft text-warning",
} as const;

export type Tone = keyof typeof TONES;

export function Badge({
  tone = "neutral",
  className,
  children,
}: {
  tone?: Tone;
  className?: string;
  children: ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex min-w-0 max-w-full items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-medium leading-4",
        TONES[tone],
        className,
      )}
    >
      <span className="min-w-0 truncate">{children}</span>
    </span>
  );
}

const CALLOUT_ICON = { info: Info, warning: TriangleAlert, error: OctagonAlert } as const;
const CALLOUT_TONE = {
  info: "border-primary/20 bg-primary-soft text-fg [&_svg]:text-primary",
  warning: "border-warning/25 bg-warning-soft text-fg [&_svg]:text-warning",
  error: "border-negative/25 bg-negative-soft text-fg [&_svg]:text-negative",
} as const;

export function Callout({
  kind = "info",
  children,
  className,
}: {
  kind?: keyof typeof CALLOUT_ICON;
  children: ReactNode;
  className?: string;
}) {
  const Icon = CALLOUT_ICON[kind];
  return (
    <div
      role={kind === "error" ? "alert" : "note"}
      className={cn(
        "flex items-start gap-2.5 rounded-lg border px-3 py-2.5 text-sm leading-relaxed",
        CALLOUT_TONE[kind],
        className,
      )}
    >
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div className="min-w-0 flex-1 break-words [overflow-wrap:anywhere]">{children}</div>
    </div>
  );
}

export function SectionLabel({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "text-[11px] font-medium uppercase tracking-[0.08em] text-subtle",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** The app mark: a rising filing line in the primary colour. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={cn("size-7", className)}>
      <rect width="32" height="32" rx="8" className="fill-surface-2 stroke-border" strokeWidth="1" />
      <path
        d="M8 22l5-6 4 3 7-9"
        fill="none"
        className="stroke-primary"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="24" cy="10" r="2" className="fill-primary" />
    </svg>
  );
}
