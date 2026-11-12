import { Check, MessageCircleQuestion } from "lucide-react";
import { slugNote, type ClarifyChoice } from "@/lib/clarify";
import { cn } from "@/lib/format";
import { useRegionName } from "./answer-scope";

const FALLBACK_PROMPT = "Which one do you mean?";

/**
 * One open question with a button per candidate. A button sends the
 * candidate's catalog slug as the next analyst message (ADR 0006); only the
 * latest turn's buttons are live, and only while the thread holds the question.
 */
export function Clarify({
  prompt,
  choices,
  live,
  onChoose,
}: {
  prompt: string | null;
  choices: ClarifyChoice[];
  live: boolean;
  onChoose: (slug: string) => void;
}) {
  const answered = choices.some((choice) => choice.chosen);
  const note = live
    ? "Nothing has been fetched yet. Pick one to continue."
    : answered
      ? "Answered below."
      : "This question was set aside.";
  const name = useRegionName("Clarify");
  return (
    <section
      aria-label={name}
      className={cn(
        "relative overflow-hidden rounded-xl border bg-surface",
        live ? "border-primary/30 shadow-[0_18px_40px_-30px_var(--primary)]" : "border-border",
      )}
    >
      {live && (
        <span
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/70 to-transparent"
        />
      )}
      <div className="flex items-start gap-3 px-4 pt-4 sm:px-5">
        <span
          className={cn(
            "flex size-8 shrink-0 items-center justify-center rounded-lg",
            live ? "bg-primary-soft text-primary" : "bg-surface-2 text-subtle",
          )}
        >
          <MessageCircleQuestion className="size-4" aria-hidden />
        </span>
        <div className="min-w-0 pt-0.5">
          <h3 className={cn("text-[15px] font-medium leading-snug", live ? "text-fg" : "text-muted")}>
            {prompt || FALLBACK_PROMPT}
          </h3>
          <p className="mt-0.5 text-[13px] text-subtle">{note}</p>
        </div>
      </div>
      <div
        role="group"
        aria-label="Candidates"
        className="grid gap-2 px-4 pb-4 pt-3.5 sm:flex sm:flex-wrap sm:pl-16 sm:pr-5"
      >
        {choices.map((choice) => (
          <button
            key={choice.slug}
            type="button"
            disabled={!live}
            onClick={() => onChoose(choice.slug)}
            className={cn(
              "group flex min-h-11 items-center justify-between gap-4 rounded-lg border px-3.5 py-2 text-left transition-[background,border,box-shadow,color] sm:min-w-40",
              live &&
                "border-border-strong bg-surface-2/60 hover:border-primary/60 hover:bg-primary-soft hover:shadow-[0_0_0_3px] hover:shadow-primary/10",
              !live && choice.chosen && "border-primary/35 bg-primary-soft",
              !live && !choice.chosen && "border-border bg-transparent opacity-55",
              "disabled:cursor-not-allowed",
            )}
          >
            <span className="min-w-0">
              <span
                className={cn(
                  "block text-[13.5px] font-medium leading-tight",
                  live ? "text-fg group-hover:text-primary" : choice.chosen ? "text-primary" : "text-muted",
                )}
              >
                {choice.label}
              </span>
              <SlugNote choice={choice} />
            </span>
            {choice.chosen && <Check className="size-4 shrink-0 text-primary" aria-label="Chosen" />}
          </button>
        ))}
      </div>
    </section>
  );
}

/** What the button sends, as words, when the label does not already say them. */
function SlugNote({ choice }: { choice: ClarifyChoice }) {
  const note = slugNote(choice.slug, choice.label);
  return note && <span className="num mt-0.5 block text-[10.5px] text-subtle">{note}</span>;
}
