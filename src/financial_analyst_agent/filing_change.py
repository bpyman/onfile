"""Accession-pinned filing-section comparison. The model does not pick filings or rewrite diffs."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable
from datetime import date
from difflib import SequenceMatcher
from html.parser import HTMLParser
from typing import Any, Literal
from urllib.parse import quote

from financial_analyst_agent.contracts import (
    MODEL_ANALYSIS_BANNER,
    DisclosureChange,
    Intent,
    RendererKind,
    Runtime,
    ToolTrace,
    TurnResult,
    refusal_from_error,
)
from financial_analyst_agent.domain.enums import PERIODIC_FORMS
from financial_analyst_agent.domain.errors import (
    SOURCE_FAILURES,
    AmbiguousCompanyError,
    CompanyNotFoundError,
    FinancialAnalystError,
    ProviderError,
    ProviderRefusal,
    visitor_message,
)
from financial_analyst_agent.graph.state import FilingChangeRequest
from financial_analyst_agent.guide import format_date, joined, short_name
from financial_analyst_agent.observability import call_provider
from financial_analyst_agent.providers.sec.company_resolver import resolve_company
from financial_analyst_agent.providers.sec.submissions import (
    ACCESSION_PATTERN,
    require_recent_filings,
)
from financial_analyst_agent.providers.sec.urls import build_filing_document_url
from financial_analyst_agent.universe import sec_identity_is_operating

SectionId = Literal["mda", "risk_factors"]

REVIEWED_SECTIONS: tuple[SectionId, ...] = ("mda", "risk_factors")
SECTION_LABELS: dict[SectionId, str] = {
    "mda": "Management's Discussion and Analysis",
    "risk_factors": "Risk Factors",
}
_SECTION_HEADINGS: dict[SectionId, re.Pattern[str]] = {
    "mda": re.compile(
        r"item\s+(?:2|7)\s*[.:—–-]?\s*management['’]?s?\s+discussion",
        re.IGNORECASE,
    ),
    "risk_factors": re.compile(r"item\s+1a\s*[.:—–-]?\s*risk\s+factors", re.IGNORECASE),
}
_NEXT_ITEM = re.compile(r"^item\s+\d+[a-z]?(?=[\s.:—–-]|$)", re.IGNORECASE | re.MULTILINE)
# A bare "Item 2" line, no punctuation or title, repeated down the pages is a
# running header (Microsoft prints one on every page), not the next section.
_BARE_ITEM = re.compile(r"^item\s+\d+[a-z]?$", re.IGNORECASE | re.MULTILINE)
_RUNNING_HEADER_REPEATS = 3
# Disclosure on the heading's own line ("Item 1A. Risk Factors. There have been
# no material changes..."): a full stop, then a sentence ending in one.
_SENTENCE = re.compile(r"\.\s+[A-Za-z].*\w\.\s*$")
# A contents entry taken for a section: nothing under its heading but a page.
_STUB_BODY = re.compile(r"^\W*(?:pages?\s*)?\d{0,3}(?:\s*[-–]\s*\d{1,3})?\W*$", re.IGNORECASE)
# What may precede a heading on its line: "PART II — OTHER INFORMATION Item 1A. …".
_PART_LABEL = re.compile(r"part\s+i{1,2}\b.{0,60}", re.IGNORECASE)
_SECTION_ALIASES: dict[str, SectionId] = {
    "md&a": "mda",
    "mda": "mda",
    "management's discussion": "mda",
    "management discussion": "mda",
    "risk factors": "risk_factors",
    "risk factor": "risk_factors",
    "risk_factors": "risk_factors",
}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._skip = True
        if tag in {"p", "div", "br", "tr", "h1", "h2", "h3", "h4"}:
            self._chunks.append("\n")
        elif tag in {"td", "th"}:
            # "Noninterest revenue" and "$24,470" are two cells, not one word.
            self._chunks.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self._skip = False
        if tag in {"p", "div", "h1", "h2", "h3", "h4"}:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._chunks.append(data)

    def text(self) -> str:
        return "".join(self._chunks)


def filing_anchor_url(url: str, snippet: str) -> str:
    """Point a filing URL at the reviewed section or changed paragraph."""
    text = " ".join(snippet.split())
    if not url or not text:
        return url
    if "#:~:text=" in url:
        return url
    return f"{url}#:~:text={quote(text[:96], safe='')}"


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    lines = [" ".join(line.split()) for line in parser.text().splitlines()]
    return "\n".join(line for line in lines if line)


def _starts_line(text: str, start: int) -> bool:
    """Whether a heading match opens its line, as a heading does.

    A cross-reference ("see the Item 1A. Risk Factors section of our 2025 Form
    10-K") sits mid-sentence; taken as a heading, it ran to the next Item and
    filed pages of MD&A under Risk Factors.
    """
    before = text[text.rfind("\n", 0, start) + 1 : start].strip()
    return not before or _PART_LABEL.fullmatch(before) is not None


# An MD&A shorter than this under its Item heading is a contents entry, not the section.
_SHORT_MDA = 2000


def extract_section(html: str, section: SectionId) -> str:
    return _section_from_text(html_to_text(html), section)


def _section_from_text(text: str, section: SectionId) -> str:
    found = _section_under_item(text, section)
    if section == "mda" and len(found) < _SHORT_MDA:
        # Banks and some others (JPMorgan, Wells Fargo, Intel) file MD&A under
        # their own headings and list it only in the table of contents.
        from_contents = _mda_from_contents(text)
        if len(from_contents) > len(found):
            return from_contents
    return found


def _section_under_item(text: str, section: SectionId) -> str:
    heading = _SECTION_HEADINGS[section]
    bare = Counter(line.casefold() for line in _BARE_ITEM.findall(text))
    running = {line for line, count in bare.items() if count >= _RUNNING_HEADER_REPEATS}
    candidates: list[str] = []
    for match in heading.finditer(text):
        if not _starts_line(text, match.start()):
            continue
        end = len(text)
        for next_item in _NEXT_ITEM.finditer(text, match.end()):
            line_end = text.find("\n", next_item.start())
            line = text[next_item.start() : len(text) if line_end < 0 else line_end]
            if line.strip().casefold() in running:
                continue
            if heading.match(text, next_item.start()) is None:
                end = next_item.start()
                break
        found = text[match.start() : end].strip()
        body = found.split("\n", 1)[1] if "\n" in found else ""
        same_line = found.split("\n", 1)[0][match.end() - match.start() :]
        if _STUB_BODY.fullmatch(body.strip()) and not _SENTENCE.search(same_line):
            continue
        candidates.append(found)
    return max(candidates, key=len, default="")


_MDA_TITLE = re.compile(
    r"^(?:item\s*[27]\s*[.:—–-]?\s*)?management['’]?s\s+discussion\s+and\s+analysis\b",
    re.IGNORECASE,
)
_SPLIT_ITEM = re.compile(r"item\s*[27]\s*[.:]?", re.IGNORECASE)
_LINE_ITEM = re.compile(r"^item\s*\d+[a-z]?\b", re.IGNORECASE)
_PAGE = re.compile(r"^(?:pages?\s+)?(\d{1,3})(?:\s*[-–]\s*\d{1,3})?$", re.IGNORECASE)
# Contents entries: a title of at most this many characters, then its page on the next line.
_MAX_TITLE = 120
# A listed MD&A part this many pages past the one before it (a glossary at the
# back of the report) is not where MD&A ends.
_OUTLYING_PAGES = 40
# Unpaired lines ("Part II", "Page") a contents page may have between entries.
_CONTENTS_GAP = 4


def _norm_title(line: str) -> str:
    return " ".join(line.strip(" .:").casefold().replace("’", "'").split())


class _Contents:
    """The table of contents in a filing's text lines: titles followed by page numbers."""

    def __init__(self, lines: list[str]) -> None:
        self.lines = lines

    def page(self, k: int) -> int | None:
        if not 0 <= k < len(self.lines):
            return None
        match = _PAGE.match(self.lines[k].strip())
        return int(match.group(1)) if match else None

    def is_entry(self, k: int) -> bool:
        title = self.lines[k].strip()
        return (
            self.page(k + 1) is not None
            and 2 < len(title) <= _MAX_TITLE
            and self.page(k) is None
            and not title.startswith(("(", "•"))
        )

    def entries(self, k: int, step: int, stop: int) -> list[int]:
        found: list[int] = []
        gap = 0
        while 0 <= k < stop and gap <= _CONTENTS_GAP:
            if self.is_entry(k):
                gap = 0
                found.append(k)
            else:
                gap += 1
            k += step
        return found


def _mda_from_contents(text: str) -> str:
    """MD&A found through the table of contents, for filings with no Item 2 heading over it.

    The contents list MD&A's parts with their pages ("Executive Overview 5");
    the body uses those parts as headings. MD&A runs from its first heading
    to the heading of the next contents entry by page.
    """
    lines = text.split("\n")
    contents = _Contents(lines)
    for i, line in enumerate(lines):
        split = _SPLIT_ITEM.fullmatch(line.strip()) is not None and i + 1 < len(lines)
        title = f"{line} {lines[i + 1]}" if split else line
        if not _MDA_TITLE.match(title.strip()):
            continue
        j = i + 1 + int(split)
        parts: list[tuple[str, int]] = []
        while j < len(lines) and contents.is_entry(j) and not _LINE_ITEM.match(lines[j].strip()):
            page = contents.page(j + 1)
            assert page is not None
            parts.append((_norm_title(lines[j]), page))
            j += 2
        if len(parts) < 2:
            continue
        part_titles = {part for part, _ in parts}
        start = next(
            (
                k
                for k in range(j, len(lines))
                if not contents.is_entry(k)
                and not _LINE_ITEM.match(lines[k].strip())
                and (_MDA_TITLE.match(lines[k].strip()) or _norm_title(lines[k]) in part_titles)
            ),
            None,
        )
        if start is None:
            return ""
        # Other entries of the same contents page, before MD&A's entry and after
        # it up to where the body starts.
        indexes = contents.entries(i - 1, -1, len(lines)) + contents.entries(j, 1, start)
        pages = sorted(page for _, page in parts)
        while len(pages) > 1 and pages[-1] - pages[-2] > _OUTLYING_PAGES:
            pages.pop()
        after: dict[str, int] = {}
        for k in indexes:
            title_k, page_k = _norm_title(lines[k]), contents.page(k + 1)
            if page_k is not None and page_k > pages[-1] and title_k not in part_titles:
                after.setdefault(title_k, page_k)
        return "\n".join(lines[start : _mda_end(lines, contents, start, after)]).strip()
    return ""


def _mda_end(lines: list[str], contents: _Contents, start: int, after: dict[str, int]) -> int:
    """The line where the next contents entry's heading, or an Item heading, begins."""
    titles = [title for title in after if len(title) >= 8]
    for k in range(start + 3, len(lines)):
        line = _norm_title(lines[k])
        heading = len(line) >= 8 and any(
            (line.startswith(title) and len(line) <= len(title) + 25) or title.startswith(line)
            for title in titles
        )
        if heading or (_LINE_ITEM.match(lines[k].strip()) and not contents.is_entry(k)):
            return k
    # No heading found: stop after the footer of the page before the next entry.
    if after:
        last_page = min(after.values()) - 1
        for k in range(start + 3, len(lines)):
            if contents.page(k) == last_page:
                return k + 1
    return len(lines)


# A filing pair can differ in hundreds of paragraphs (JPMorgan: 367, 524 KB).
MAX_CHANGES_SHOWN = 60
_SUMMARIZED_CHANGES = 30
_SUMMARY_TEXT_CHARS = 1500


def _blocks(section_text: str) -> list[str]:
    blocks = [part.strip() for part in re.split(r"\n{2,}", section_text) if part.strip()]
    if len(blocks) <= 1:
        blocks = [line.strip() for line in section_text.splitlines() if line.strip()]
    return [block for block in blocks if len(block) > 20 or block.lower().startswith("item")]


def _paragraphs(section_text: str) -> list[str]:
    """The section's prose: no running footers, headings, or rows that are mostly figures."""
    blocks = _blocks(section_text)
    # A running footer repeats word for word but for its page number ("Apple Inc. |
    # Q3 2026 Form 10-Q | 18", "37 Honeywell International Inc."); a segment's
    # "Revenue increased $7.9 billion" repeats only its wording, and each is a
    # disclosure.
    repeats = Counter(_unpaged(block) for block in blocks)
    return [
        block
        for block in blocks
        if repeats[_unpaged(block)] < _RUNNING_HEADER_REPEATS
        and not _is_figures(block)
        # A heading on its own is where a disclosure sits, not one.
        and not _is_heading(block)
    ]


def _unpaged(block: str) -> str:
    return _PAGE_NUMBER.sub("", _LEADING_PAGE_NUMBER.sub("", block))


def _subsections(section_text: str) -> dict[str, str]:
    """Each paragraph's heading: the last heading-like line above it in the section."""
    under: dict[str, str] = {}
    heading = ""
    lines = [line.strip() for line in section_text.splitlines() if line.strip()]
    repeats = Counter(lines)
    for index, line in enumerate(lines):
        following = lines[index + 1] if index + 1 < len(lines) else ""
        if (
            _is_heading(line)
            # A running header ("PART I") or a table's column label ("Percentage").
            and repeats[line] < _RUNNING_HEADER_REPEATS
            and not _PART_LABEL.fullmatch(line)
            and not _is_figures(following)
        ):
            heading = _readable_heading(line)
        else:
            if _FORWARD_LOOKING.search(heading) and not _FORWARD_LOOKING.search(line):
                # The forward-looking note ends where its subject does: Microsoft's
                # MD&A introduction follows it with no heading of its own.
                heading = ""
            under.setdefault(line, heading)
    for block in _blocks(section_text):
        # A block of several lines sits under its first line's heading.
        under.setdefault(block, under.get(block.splitlines()[0].strip(), ""))
    return under


def _readable_heading(line: str) -> str:
    """ "LIQUIDITY AND CAPITAL RESOURCES" → "Liquidity and Capital Resources"."""
    if line != line.upper():
        return line
    minor = {"and", "of", "the", "for", "in", "on", "to", "a", "an", "or", "with", "by"}
    words = []
    for index, word in enumerate(line.split()):
        lower = word.lower()
        if index and lower in minor:
            words.append(lower)
        else:
            words.append(lower[:1].upper() + lower[1:])
    return " ".join(words)


def _is_heading(line: str) -> bool:
    """ "Liquidity and Capital Resources": short, unpunctuated, mostly capitalised words."""
    if len(line) > _MAX_HEADING or line.endswith((".", ":", ";", ",")) or _is_figures(line):
        return False
    if _LINE_ITEM.match(line) or not line[:1].isalpha() or not line[:1].isupper():
        return False
    # A table row ("ROE 34%", "ROE NM NM 24 % 18 %") titled like a heading.
    if any(
        char.isdigit() or char in "%$" for char in line
    ) or _TABLE_MARKS & {word.casefold() for word in line.split()}:
        return False
    words = [word for word in line.split() if word[:1].isalpha()]
    minor = {"and", "of", "the", "for", "in", "on", "to", "a", "an", "or", "with", "by"}
    capitalised = [word for word in words if word[:1].isupper() or word.casefold() in minor]
    return 1 <= len(words) <= _HEADING_WORDS and len(capitalised) == len(words)


_MAX_HEADING = 90
_FORWARD_LOOKING = re.compile(r"forward[\s-]looking", re.IGNORECASE)
# Cells a table row holds that a heading never does: not meaningful, not applicable.
_TABLE_MARKS = frozenset({"nm", "na", "n/a"})
_HEADING_WORDS = 10


def _is_figures(block: str) -> bool:
    """A table row of amounts ("Noninterest revenue $24,470 $22,037 11 %"), not prose.

    It holds as many numbers as words; "Revenue increased $7.9 billion or 30%." is
    a sentence.
    """
    tokens = block.split()
    numbers = sum(any(char.isdigit() for char in token) for token in tokens)
    words = sum(token.isalpha() for token in tokens)
    return numbers >= 2 and numbers >= words


def _figure_rows(section_text: str) -> set[str]:
    return {
        _undated(block)
        for block in _blocks(section_text)
        if _is_figures(block)
    }


_PAGE_NUMBER = re.compile(r"[\s|•·–-]*\d{1,3}\s*$")
_LEADING_PAGE_NUMBER = re.compile(r"^\d{1,3}(?=\s+[A-Z])[\s|•·–-]*")
_MONTH = (
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December"
    r"|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\.?"
)
# Dates, years (also one run into the next word, "2024Drivers") and page
# references move from one filing to the next without the disclosure changing.
_DATES = re.compile(
    rf"\b{_MONTH}\s+\d{{1,2}},?\s+(?:19|20)\d{{2}}(?!\d)"
    r"|(?<!\d)(?:19|20)\d{2}(?!\d)"
    r"|\bpages?\s+\d{1,3}(?:\s*[-–]\s*\d{1,3})?\b",
    re.IGNORECASE,
)


def _undated(paragraph: str) -> str:
    """The paragraph with its dates and years masked, for matching across a year."""
    return _DATES.sub("<date>", " ".join(paragraph.split()))


# Typography a filing agent changes between filings: curly quotes and dashes.
_TYPOGRAPHY = str.maketrans(
    {"\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"', "\u2014": "-", "\u2013": "-"}
)
# A footnote mark glued to a word, "revenue(c)" or "(a)Included": the letters
# move as notes are added, the disclosure does not. "$(11)" is an amount.
_FOOTNOTE_MARK = re.compile(
    r"(?<=[^\s$(])\((?:[a-z]|\d{1,2})\)|(?:^|(?<=\s))\((?:[a-z]|\d{1,2})\)(?=[A-Z])"
)


def _comparable(paragraph: str) -> str:
    """The paragraph as compared: dates masked, typography and footnote marks set aside."""
    return _undated(_FOOTNOTE_MARK.sub("", paragraph.translate(_TYPOGRAPHY)))


def _words(paragraph: str) -> frozenset[str]:
    # Words alone: an edited paragraph's figures all change, its wording mostly does not.
    return frozenset(re.findall(r"[a-z][a-z']*", _comparable(paragraph).casefold()))


def _similarity(left: frozenset[str], right: frozenset[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 1.0


def _likeness(left: frozenset[str], right: frozenset[str]) -> float:
    """How alike two paragraphs are for pairing an edit.

    Shared words over all words, except that a paragraph of a few words or more
    whose words the other nearly all holds is the same one, shortened or
    expanded ("…cloud services revenue increased 11% driven by … growth of 12%"
    became "…cloud revenue increased 19%").
    """
    similar = _similarity(left, right)
    smaller = min(left, right, key=len)
    if len(smaller) >= _CONTAINED_MIN_WORDS and len(left & right) / len(smaller) >= _CONTAINED:
        return max(similar, _SAME_PARAGRAPH)
    return similar


# Paragraphs sharing this share of their words are one paragraph, edited.
_SAME_PARAGRAPH = 0.5
# A paragraph this much inside another, and at least this long, is that one edited.
_CONTAINED = 0.8
_CONTAINED_MIN_WORDS = 4
# A moved paragraph must share more to be the same one.
_MOVED_PARAGRAPH = 0.8
# Pairs scored to align a replaced run; beyond this the run is not aligned.
_MAX_PAIRINGS = 250_000


def _aligned(left: list[str], right: list[str]) -> list[tuple[int | None, int | None]]:
    """A replaced run's paragraphs paired in order by shared words; the rest unpaired.

    The diff reports a run of old paragraphs replaced by a run of new ones;
    position alone pairs a paragraph with whatever stands in its place (one
    sentence with 80 new risk factors), so each is paired with the one most
    like it, keeping their order.
    """
    n, m = len(left), len(right)
    if n * m > _MAX_PAIRINGS:
        return [(i, None) for i in range(n)] + [(None, j) for j in range(m)]
    words_left = [_words(text) for text in left]
    words_right = [_words(text) for text in right]
    score = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            similar = _likeness(words_left[i], words_right[j])
            paired = similar + score[i + 1][j + 1] if similar >= _SAME_PARAGRAPH else -1.0
            score[i][j] = max(paired, score[i + 1][j], score[i][j + 1])
    pairs: list[tuple[int | None, int | None]] = []
    i = j = 0
    while i < n and j < m:
        similar = _likeness(words_left[i], words_right[j])
        if similar >= _SAME_PARAGRAPH and score[i][j] == similar + score[i + 1][j + 1]:
            pairs.append((i, j))
            i, j = i + 1, j + 1
        elif score[i][j] == score[i + 1][j]:
            pairs.append((i, None))
            i += 1
        else:
            pairs.append((None, j))
            j += 1
    pairs.extend((index, None) for index in range(i, n))
    pairs.extend((None, index) for index in range(j, m))
    return pairs


def diff_paragraphs(
    older: str,
    newer: str,
    *,
    section: SectionId,
    older_accession: str,
    newer_accession: str,
    older_url: str,
    newer_url: str,
) -> list[DisclosureChange]:
    left = _paragraphs(older)
    right = _paragraphs(newer)
    under_left = _subsections(older)
    under_right = _subsections(newer)
    # Matched with dates masked: a paragraph that differs only by its dates ("the
    # quarter ended March 31, 2026" a year on) is the same disclosure, not a change.
    matcher = SequenceMatcher(
        a=[_comparable(text) for text in left],
        b=[_comparable(text) for text in right],
        autojunk=False,
    )
    label = SECTION_LABELS[section]

    def added(paragraph: str) -> DisclosureChange:
        return DisclosureChange(
            section=section,
            section_label=label,
            change_kind="added",
            after_text=paragraph,
            subsection=under_right.get(paragraph, ""),
            older_accession=older_accession,
            newer_accession=newer_accession,
            older_url=filing_anchor_url(older_url, label),
            newer_url=filing_anchor_url(newer_url, paragraph),
        )

    def removed(paragraph: str) -> DisclosureChange:
        return DisclosureChange(
            section=section,
            section_label=label,
            change_kind="removed",
            before_text=paragraph,
            subsection=under_left.get(paragraph, ""),
            older_accession=older_accession,
            newer_accession=newer_accession,
            older_url=filing_anchor_url(older_url, paragraph),
            newer_url=filing_anchor_url(newer_url, label),
        )

    def changed(before: str, after: str) -> DisclosureChange:
        return DisclosureChange(
            section=section,
            section_label=label,
            change_kind="changed",
            before_text=before,
            after_text=after,
            subsection=under_right.get(after, "") or under_left.get(before, ""),
            older_accession=older_accession,
            newer_accession=newer_accession,
            older_url=filing_anchor_url(older_url, before),
            newer_url=filing_anchor_url(newer_url, after),
        )

    changes: list[DisclosureChange] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        for i, j in _aligned(left[i1:i2], right[j1:j2]):
            if i is not None and j is not None:
                before, after = left[i1 + i], right[j1 + j]
                if _comparable(before) != _comparable(after):
                    changes.append(changed(before, after))
            elif j is not None:
                changes.append(added(right[j1 + j]))
            elif i is not None:
                changes.append(removed(left[i1 + i]))
    return _rejoin_moved(changes, changed)


def _rejoin_moved(
    changes: list[DisclosureChange],
    changed: Callable[[str, str], DisclosureChange],
) -> list[DisclosureChange]:
    """One change for a paragraph that moved and was edited; none for one that only moved.

    The diff sees a moved paragraph as removed in one place and added in
    another (Accenture's one-word edit to a risk it listed elsewhere).
    """
    joined: list[DisclosureChange | None] = list(changes)
    for index, item in enumerate(changes):
        if item.change_kind != "removed":
            continue
        words = _words(item.before_text)
        match = next(
            (
                other
                for other, candidate in enumerate(joined)
                if candidate is not None
                and candidate.change_kind == "added"
                and _similarity(words, _words(candidate.after_text)) >= _MOVED_PARAGRAPH
            ),
            None,
        )
        if match is None:
            continue
        after = joined[match]
        assert after is not None
        if _comparable(item.before_text) == _comparable(after.after_text):
            joined[match] = None
        else:
            joined[match] = changed(item.before_text, after.after_text)
        joined[index] = None
    return [item for item in joined if item is not None]


def cap_changes(
    changes: list[DisclosureChange], limit: int = MAX_CHANGES_SHOWN
) -> tuple[list[DisclosureChange], str]:
    """The changes shown, at most ``limit``, shared among the sections.

    Capped in filing order across the whole filing, a long MD&A (JPMorgan's 274
    changes) left Risk Factors none. Each section gets an equal share; what one
    leaves unused goes to the others. The banner says what was left out.
    """
    counts = Counter(item.section for item in changes)
    if len(changes) <= limit:
        return changes, ""
    budget = dict.fromkeys(counts, 0)
    left = limit
    while left > 0:
        open_sections = [section for section in counts if budget[section] < counts[section]]
        if not open_sections:
            break
        share = max(1, left // len(open_sections))
        for section in open_sections:
            grant = min(share, counts[section] - budget[section], left)
            budget[section] += grant
            left -= grant
    shown: list[DisclosureChange] = []
    taken = Counter[str]()
    for item in changes:
        if taken[item.section] < budget[item.section]:
            shown.append(item)
            taken[item.section] += 1
    parts = [
        f"all {counts[section]} in {SECTION_LABELS[section]}"
        if budget[section] == counts[section]
        else f"the first {budget[section]} of {counts[section]} in {SECTION_LABELS[section]}"
        for section in counts
    ]
    banner = f"Showing {joined(parts)} changes, in the order they appear in the filing."
    return shown, banner


def parse_sections(raw: str) -> tuple[SectionId, ...]:
    lowered = raw.casefold()
    found: list[SectionId] = []
    if "both" in lowered or "and risk" in lowered:
        return REVIEWED_SECTIONS
    for alias, section in _SECTION_ALIASES.items():
        if alias in lowered and section not in found:
            found.append(section)
    if not found:
        return ("mda",)
    return tuple(found)


def _primary_document(recent: dict[str, Any], accession: str) -> str:
    accessions = recent.get("accessionNumber")
    documents = recent.get("primaryDocument")
    forms = recent.get("form")
    if (
        not isinstance(accessions, list)
        or not isinstance(documents, list)
        or not isinstance(forms, list)
    ):
        raise ProviderError("submissions accessionNumber, primaryDocument and form must be lists")
    if len(accessions) != len(documents) or len(accessions) != len(forms):
        raise ProviderError("submissions filing arrays have inconsistent lengths")
    for index, candidate in enumerate(accessions):
        if candidate == accession and forms[index] in PERIODIC_FORMS:
            document = documents[index]
            if isinstance(document, str) and document.strip():
                return document
            raise ProviderRefusal(f"Primary document is missing for accession {accession}")
    raise ProviderRefusal(f"Filing accession {accession} was not found in supported submissions")


def _pretty(iso: str) -> str:
    try:
        day = date.fromisoformat(iso)
    except ValueError:
        return iso
    return format_date(day)


_YEAR = 365
_SAME_QUARTER_DAYS = 20


def _year_apart_quarterlies(
    recent: dict[str, Any], form: str = "10-Q"
) -> tuple[str, str] | None:
    """The newest report of ``form`` and the one for the same period a year before it.

    A year apart compares like with like: the same fiscal quarter, so seasonal
    wording does not read as change. Without one, the previous 10-Q stands in.
    """
    accessions = recent.get("accessionNumber")
    forms = recent.get("form")
    dates = recent.get("reportDate")
    if not (isinstance(accessions, list) and isinstance(forms, list) and isinstance(dates, list)):
        return None
    quarterlies: list[tuple[date, str]] = []
    for accession, kind, raw in zip(accessions, forms, dates, strict=False):
        if kind != form or not isinstance(raw, str) or not isinstance(accession, str):
            continue
        try:
            quarterlies.append((date.fromisoformat(raw), accession))
        except ValueError:
            continue
    quarterlies.sort(reverse=True)
    if len(quarterlies) < 2:
        return None
    newest_date, newest = quarterlies[0]
    for when, accession in quarterlies[1:]:
        if abs((newest_date - when).days - _YEAR) <= _SAME_QUARTER_DAYS:
            return accession, newest
    return quarterlies[1][1], newest


def _filing_date(recent: dict[str, Any], accession: str) -> str:
    accessions = recent.get("accessionNumber")
    if not isinstance(accessions, list):
        return ""
    dates = recent.get("reportDate")
    if not isinstance(dates, list):
        dates = recent.get("filingDate")
    if not isinstance(dates, list) or len(dates) != len(accessions):
        return ""
    for index, candidate in enumerate(accessions):
        if candidate == accession:
            value = dates[index]
            return value.strip() if isinstance(value, str) else ""
    return ""


def _order_accessions(recent: dict[str, Any], first: str, second: str) -> tuple[str, str]:
    left = _filing_date(recent, first)
    right = _filing_date(recent, second)
    if left and right and left > right:
        return second, first
    return first, second


_ANNUAL_WORDING = re.compile(r"\b10-?k\b|\bannual report\b", re.IGNORECASE)


def _form_asked(query: str) -> str:
    """ "What changed in Microsoft's latest 10-K?" compares 10-Ks; otherwise 10-Qs."""
    return "10-K" if _ANNUAL_WORDING.search(query) else "10-Q"


def _request_refusal(
    query: str, company: str, older: str, newer: str, plan: FilingChangeRequest
) -> str:
    """Why this request cannot be compared as asked, or ""."""
    found = ACCESSION_PATTERN.findall(query)
    if len(set(found)) > 2:
        return "Give exactly two accession numbers: the older filing and the newer one."
    if found and len(set(found)) == 1 and len(found) > 1:
        return "Those two accession numbers are the same filing. Give two different ones."
    others = plan.other_companies
    if others and company:
        return (
            "I compare one company's filings at a time. Ask about each company "
            "separately, for example “What changed in Apple's latest 10-Q?”."
        )
    if not company or company == "unknown":
        return (
            "I couldn't tell which company's filings to compare. Name one, for example "
            "“What changed in Apple's latest 10-Q?”, or give two of its accession numbers."
        )
    if bool(older) != bool(newer):
        return (
            "Give two accession numbers to compare, or none to compare the latest 10-Q "
            "with the one a year earlier."
        )
    return ""


def _form_of(recent: dict[str, Any], accession: str) -> str:
    for candidate, form in zip(
        recent.get("accessionNumber") or [], recent.get("form") or [], strict=False
    ):
        if candidate == accession:
            return str(form)
    return ""


def _check_reviewable(recent: dict[str, Any], accession: str) -> None:
    """Refuse an accession that is this company's, but not a 10-Q or 10-K."""
    form = _form_of(recent, accession)
    if form and form not in PERIODIC_FORMS:
        raise ProviderRefusal(
            f"Accession {accession} is a {form}, not a 10-Q or 10-K; only quarterly and "
            "annual reports are compared."
        )


def _chosen_pair_banner(recent: dict[str, Any], name: str, first: str, second: str) -> str:
    """Say which reports two given accession numbers are, and when they differ in kind."""
    older, newer = _order_accessions(recent, first, second)
    parts = [
        f"its {_form_of(recent, accession) or 'filing'} for the period ended "
        f"{_pretty(_filing_date(recent, accession))}"
        for accession in (older, newer)
    ]
    banner = f"Comparing {short_name(name)}'s {parts[0].removeprefix('its ')} with {parts[1]}."
    kinds = {_form_of(recent, accession).removesuffix("/A") for accession in (older, newer)}
    if len(kinds) > 1:
        banner += " A 10-K and a 10-Q are laid out differently, so more reads as changed."
    return banner


def _too_few_message(recent: dict[str, Any], name: str, form: str) -> str:
    forms = set(recent.get("form") or [])
    if forms & {"20-F", "40-F"} and "10-Q" not in forms:
        return (
            f"{short_name(name)} files annual 20-F or 40-F reports with the SEC rather "
            "than 10-Qs, so there are no quarterly reports to compare."
        )
    return f"Fewer than two {form} filings are available for this company."


def _accessions_from_query(query: str, plan_older: str, plan_newer: str) -> tuple[str, str]:
    found = ACCESSION_PATTERN.findall(query)
    if query.strip():
        if len(found) >= 2:
            return found[0], found[1]
        if found:
            return found[0], ""
        return "", ""
    return plan_older, plan_newer


# Whole words only: "Verisk", "Riskified" and "Waste Management" name companies,
# not sections.
_RISK_WORDS = r"risk\s+factors?|risks?"
_MDA_WORDS = r"md&a|mda|management['’]?s?\s+discussion(?:\s+and\s+analysis)?"
_NEGATION = (
    r"(?:not|no|excluding|exclude|except|without|other\s+than|but\s+not)\s+(?:the\s+|its\s+)?"
)
_RISK = re.compile(rf"\b(?:{_RISK_WORDS})\b", re.IGNORECASE)
_MDA = re.compile(rf"(?<![\w&])(?:{_MDA_WORDS})\b", re.IGNORECASE)
_NOT_RISK = re.compile(rf"\b{_NEGATION}(?:{_RISK_WORDS})\b", re.IGNORECASE)
_NOT_MDA = re.compile(rf"\b{_NEGATION}(?:{_MDA_WORDS})\b", re.IGNORECASE)


def requested_sections(text: str) -> tuple[SectionId, ...] | None:
    """The reviewed sections a question names, or None when it names neither.

    "MD&A, not the risk factors" and "excluding risk factors" leave a section
    out; a question naming neither asks about the whole filing.
    """
    risk = _RISK.search(text) is not None and _NOT_RISK.search(text) is None
    mda = _MDA.search(text) is not None and _NOT_MDA.search(text) is None
    excluded_risk = _NOT_RISK.search(text) is not None
    excluded_mda = _NOT_MDA.search(text) is not None
    if risk and mda:
        return REVIEWED_SECTIONS
    if risk or (excluded_mda and not mda):
        return ("risk_factors",)
    if mda or excluded_risk:
        return ("mda",)
    if re.search(r"\bboth\b", text, re.IGNORECASE):
        return REVIEWED_SECTIONS
    return None


def _labels(sections: list[SectionId]) -> str:
    return " and ".join(SECTION_LABELS[section] for section in sections)


# A filing that could not be fetched or read is not one whose sections are absent.
FILINGS_UNREADABLE_MESSAGE = (
    "I couldn't read the filings from SEC EDGAR just now, so they were not compared. "
    "Please try again in a few minutes."
)
SUMMARY_UNAVAILABLE_MESSAGE = "The model's summary could not be written just now."


def _public_message(exc: BaseException) -> str:
    """A refusal written for the visitor as it is; a source failure in plain words."""
    return visitor_message(exc, FILINGS_UNREADABLE_MESSAGE)


def _unreadable_sentence(unreadable: list[SectionId]) -> str:
    noun = "section" if len(unreadable) == 1 else "sections"
    missing = " or ".join(SECTION_LABELS[section] for section in unreadable)
    return f"I couldn't find the {missing} {noun} in one or both of these filings"


def _unchanged_message(compared: list[SectionId], unreadable: list[SectionId]) -> str:
    if not unreadable:
        return "No reviewed-section changes were found between those filings."
    if not compared:
        pronoun = "it" if len(unreadable) == 1 else "them"
        return f"{_unreadable_sentence(unreadable)}, so I couldn't compare {pronoun}."
    return (
        f"{_labels(compared)} did not change between these filings. "
        f"{_unreadable_sentence(unreadable)}, so it was not compared."
    )


def run_filing_change(
    plan: FilingChangeRequest, runtime: Runtime, *, query: str = ""
) -> TurnResult:
    company = plan.company
    older, newer = _accessions_from_query(query, plan.older_accession, plan.newer_accession)
    sections = requested_sections(query) or parse_sections(plan.section)
    traces = [
        ToolTrace(
            tool="filing_change",
            args={
                "company": company,
                "older_accession": older,
                "newer_accession": newer,
                "sections": list(sections),
            },
        )
    ]
    refused = _request_refusal(query, company, older, newer, plan)
    if refused:
        return TurnResult(
            intent=Intent.FILING_CHANGE,
            tool_traces=traces,
            renderer=RendererKind.REFUSE,
            message=refused,
        )
    form = _form_asked(query)
    filings = runtime.filings
    if filings is None:
        return TurnResult(
            intent=Intent.FILING_CHANGE,
            tool_traces=traces,
            renderer=RendererKind.REFUSE,
            message="Filing documents are not available on this runtime.",
        )
    try:
        resolved = resolve_company(company, filings.get_company_tickers())
    except (CompanyNotFoundError, AmbiguousCompanyError, *SOURCE_FAILURES) as exc:
        return TurnResult(
            intent=Intent.FILING_CHANGE,
            tool_traces=traces,
            renderer=RendererKind.REFUSE,
            message=_public_message(exc),
            refusal=(
                refusal_from_error(exc)
                if isinstance(exc, FinancialAnalystError)
                else None
            ),
        )
    cik = resolved.cik
    if not sec_identity_is_operating(cik, resolved.name):
        # The same membership rule lookups and rankings apply (ADR 0001, 0002).
        return TurnResult(
            intent=Intent.FILING_CHANGE,
            tool_traces=traces,
            renderer=RendererKind.REFUSE,
            message=(
                f"{resolved.name} is not an operating company (it is a fund, business "
                "development company or similar listing), so its filings are outside "
                "what this analyst covers."
            ),
        )
    # SEC titles companies "PFIZER INC"; the snapshot knows them as "Pfizer Inc.".
    display = getattr(runtime.facts, "display_name", None)
    name = display(cik, resolved.name) if callable(display) else resolved.name
    chosen_banner = ""
    changes: list[DisclosureChange] = []
    figure_rows = 0
    section_errors: list[str] = []
    compared: list[SectionId] = []
    unreadable: list[SectionId] = []
    try:
        recent = require_recent_filings(filings.get_submissions(cik))
        if not older:
            pair = _year_apart_quarterlies(recent, form)
            if pair is None:
                raise ProviderRefusal(_too_few_message(recent, name, form))
            older, newer = pair
            period = "quarter" if form == "10-Q" else "year"
            chosen_banner = (
                f"Comparing {short_name(name)}'s latest {form} ({period} ended "
                f"{_pretty(_filing_date(recent, newer))}) with the one for "
                f"{_pretty(_filing_date(recent, older))}."
            )
        else:
            for accession in (older, newer):
                _check_reviewable(recent, accession)
            chosen_banner = _chosen_pair_banner(recent, name, older, newer)
        older, newer = _order_accessions(recent, older, newer)
        traces[0] = traces[0].model_copy(
            update={
                "args": {
                    **traces[0].args,
                    "older_accession": older,
                    "newer_accession": newer,
                }
            }
        )
        older_doc = _primary_document(recent, older)
        newer_doc = _primary_document(recent, newer)
        older_text = html_to_text(filings.get_filing_document(cik, older, older_doc))
        newer_text = html_to_text(filings.get_filing_document(cik, newer, newer_doc))
        older_url = build_filing_document_url(cik, older, older_doc)
        newer_url = build_filing_document_url(cik, newer, newer_doc)
        for section in sections:
            older_section = _section_from_text(older_text, section)
            newer_section = _section_from_text(newer_text, section)
            if not older_section or not newer_section:
                section_errors.append(f"{SECTION_LABELS[section]} was not found")
                unreadable.append(section)
                continue
            compared.append(section)
            figure_rows += len(_figure_rows(newer_section) - _figure_rows(older_section))
            changes.extend(
                diff_paragraphs(
                    older_section,
                    newer_section,
                    section=section,
                    older_accession=older,
                    newer_accession=newer,
                    older_url=older_url,
                    newer_url=newer_url,
                )
            )
    except SOURCE_FAILURES as exc:
        code = exc.code if isinstance(exc, ProviderError) else ProviderError.code
        traces[0] = traces[0].model_copy(
            update={"provenance": {"error": {"code": code, "message": _public_message(exc)}}}
        )
        return TurnResult(
            intent=Intent.FILING_CHANGE,
            tool_traces=traces,
            renderer=RendererKind.REFUSE,
            message=_public_message(exc),
            refusal=(
                refusal_from_error(exc)
                if isinstance(exc, FinancialAnalystError)
                else None
            ),
        )
    traces[0] = traces[0].model_copy(
        update={
            "provenance": {
                "change_count": len(changes),
                "cik": cik,
                **({"section_errors": section_errors} if section_errors else {}),
            }
        }
    )
    if not changes:
        # "No changes" is claimed only for sections both filings let us compare.
        return TurnResult(
            intent=Intent.FILING_CHANGE,
            tool_traces=traces,
            renderer=RendererKind.REFUSE,
            message=_unchanged_message(compared, unreadable),
        )
    banners: list[str] = [chosen_banner] if chosen_banner else []
    if unreadable:
        banners.append(
            _unreadable_sentence(unreadable)
            + f", so only {_labels(compared)} was compared."
        )
    if figure_rows:
        rows = "row" if figure_rows == 1 else "rows"
        banners.append(
            f"{figure_rows} table {rows} of figures changed too and are left out here; "
            "ask for a metric to see the figures with their sources."
        )
    changes, capped = cap_changes(changes)
    if capped:
        banners.append(capped)
    # The model reads the first changes of each section, shared as the list is,
    # each cut to a length it can weigh: a long MD&A must not crowd out Risk Factors.
    summarized, _ = cap_changes(changes, _SUMMARIZED_CHANGES)
    grounding = json.dumps(
        [
            item.model_copy(
                update={
                    "before_text": item.before_text[:_SUMMARY_TEXT_CHARS],
                    "after_text": item.after_text[:_SUMMARY_TEXT_CHARS],
                }
            ).model_dump(mode="json")
            for item in summarized
        ],
        default=str,
    )
    essay = None
    extras: list[str] = []
    if runtime.essay is not None and plan.summarize:
        from financial_analyst_agent.turn import _numeral_lock_extras

        topic = (
            f"Summarize only the following disclosure changes for {name}. "
            "Do not invent numbers."
        )
        essay_completer = runtime.essay
        try:
            essay = call_provider(
                "llm", lambda: essay_completer.complete_essay(topic, grounding)
            )
            extras = _numeral_lock_extras(essay, grounding)
            if extras:
                # The summary is withheld; say why rather than label nothing. The
                # turn itself succeeds, so the extras go on the trace, not the result
                # (numeral-lock extras are empty on a successful turn).
                essay = None
                traces[0] = traces[0].model_copy(
                    update={
                        "provenance": {**traces[0].provenance, "summary_numeral_lock": extras}
                    }
                )
                banners.append(
                    "The model's summary was withheld because it quoted numbers "
                    "that are not in these filings."
                )
            else:
                banners.append(MODEL_ANALYSIS_BANNER)
        except ProviderError as exc:
            # The changes stand on their own; say plainly why no summary is shown.
            essay = None
            banners.append(visitor_message(exc, SUMMARY_UNAVAILABLE_MESSAGE))
    return TurnResult(
        intent=Intent.FILING_CHANGE,
        tool_traces=traces,
        renderer=RendererKind.TABLE,
        disclosure_changes=changes,
        essay=essay,
        banners=banners,
    )
