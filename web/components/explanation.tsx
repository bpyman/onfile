import { ChevronDown, FileText, Sparkles } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/format";
import type { DisplayCompanyExplanation, DisplayExplanation } from "@/lib/types";
import { useRegionName } from "./answer-scope";
import { Callout, ExternalLink } from "./ui";

// explanation.NOT_FOUND_MESSAGE: what shows when an answer carries neither paragraphs nor a line.
const NOT_FOUND = "I couldn't find management's explanation in this 10-Q";

/**
 * Management's explanation (ADR 0017): for each company, the 10-Q its figure came
 * from, the model's short explanation, then the MD&A paragraphs it chose, verbatim,
 * each linked to its place in the filing. On a phone the paragraphs wait behind
 * "Show the paragraphs". Where there is no explanation, the line says why and links
 * the MD&A.
 */
export function ManagementExplanation({ explanation }: { explanation: DisplayExplanation }) {
  const name = useRegionName(explanation.heading);
  return (
    <section aria-label={name} className="overflow-hidden rounded-xl border border-border bg-surface">
      <header className="flex items-center gap-2 border-b border-border px-4 py-2.5 text-[13px] font-medium text-fg sm:px-5">
        <FileText className="size-4 text-primary" aria-hidden />
        {explanation.heading}
      </header>
      {explanation.note && (
        <div className="border-b border-border px-4 py-3 sm:px-5">
          <Callout kind="info">{`${explanation.note}.`}</Callout>
        </div>
      )}
      <div className="divide-y divide-border">
        {explanation.companies.map((company) => (
          <CompanyExplanation key={`${company.company_name}-${company.filing_url}`} company={company} />
        ))}
      </div>
    </section>
  );
}

function CompanyExplanation({ company }: { company: DisplayCompanyExplanation }) {
  const [open, setOpen] = useState(false);
  // "From Apple's 10-Q for the quarter ended Jun 27, 2026 · MD&A": the section links to the MD&A.
  const [from, section] = company.source.split(" · ");
  const shown = company.paragraphs.length > 0 && !company.unavailable;
  return (
    <article className="space-y-3 px-4 py-4 sm:px-5">
      <p className="text-[12.5px] leading-relaxed text-muted">
        {from}
        {section && (
          <>
            {" · "}
            <ExternalLink href={company.mda_url} className="text-[12.5px]">
              {section}
            </ExternalLink>
          </>
        )}
      </p>
      {shown ? (
        <>
          <div className="space-y-1.5">
            <p className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-[0.08em] text-subtle">
              <Sparkles className="size-3.5 text-primary" aria-hidden />
              Written by the model from the quoted paragraphs
            </p>
            <p className="max-w-[68ch] break-words text-[15px] leading-[1.7] text-fg">{company.explanation}</p>
          </div>
          <button
            type="button"
            aria-expanded={open}
            onClick={() => setOpen((value) => !value)}
            className="inline-flex items-center gap-1.5 text-[13px] font-medium text-primary sm:hidden"
          >
            <ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} aria-hidden />
            {open ? "Hide the paragraphs" : "Show the paragraphs"}
          </button>
          <ol className={cn("space-y-3", !open && "hidden sm:block")}>
            {company.paragraphs.map((paragraph) => (
              <li key={paragraph.url} className="space-y-1.5">
                <blockquote className="max-w-[72ch] border-l-2 border-primary/40 pl-3.5 text-[14px] leading-[1.7] text-muted [overflow-wrap:anywhere]">
                  {paragraph.text}
                </blockquote>
                <div className="pl-4">
                  <ExternalLink href={paragraph.url} className="text-[12.5px]">
                    Read in the filing
                  </ExternalLink>
                </div>
              </li>
            ))}
          </ol>
        </>
      ) : (
        <p className="text-[14px] leading-relaxed text-fg">
          {`${company.unavailable ?? NOT_FOUND}. `}
          <ExternalLink href={company.mda_url}>Read the MD&amp;A</ExternalLink>
        </p>
      )}
    </article>
  );
}
