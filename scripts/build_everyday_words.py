"""Build data/everyday_words.txt: words 10-Q filings write in lower case.

Some companies are named by an ordinary word: Target, Block, Gap, Match. The
issuer index must tell "Target's revenue" from "Nvidia's target margin", so it
needs to know which one-word names are also everyday words. Frequency alone
cannot say: "Nvidia" and "Pfizer" appear in many filings, always capitalised.
Case can. A word that filings mostly write in lower case in the middle of a
sentence is everyday English; a word they capitalise there is a name.

Usage: uv run python scripts/build_everyday_words.py [--sample N]
Reads the latest 10-Q of N companies spread across the universe snapshot's
market-cap ranks (fetched once into .cache/sec-corpus/, SEC_USER_AGENT needed).
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from financial_analyst_agent.config import get_settings
from financial_analyst_agent.filing_change import html_to_text
from financial_analyst_agent.providers.sec.client import SECClient
from financial_analyst_agent.universe import DEFAULT_SNAPSHOT_PATH

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = DEFAULT_SNAPSHOT_PATH
OUT = ROOT / "src/financial_analyst_agent/data/everyday_words.txt"
CORPUS = ROOT / ".cache/sec-corpus"
# Share of filings that must write the word in lower case mid-sentence.
MIN_SHARE = 0.02
# Of a word's mid-sentence uses, the share in lower case that makes it everyday.
MIN_LOWER_SHARE = 0.5
_WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
# A word after one of these starts a sentence, so its capital says nothing.
_SENTENCE_END = re.compile(r"[.!?:;•]\s*$")


def _sample(size: int) -> list[dict[str, str]]:
    companies = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["companies"]
    ranked = sorted(companies, key=lambda company: float(company["market_cap"]), reverse=True)
    step = max(1, len(ranked) // size)
    return ranked[::step][:size]


def _fetch(client: SECClient, cik: str) -> str | None:
    path = CORPUS / f"{cik}.htm"
    if path.exists():
        return path.read_text(encoding="utf-8", errors="ignore")
    recent = client.get_submissions(cik, with_history=False)["filings"]["recent"]
    for form, accession, document in zip(
        recent["form"], recent["accessionNumber"], recent["primaryDocument"], strict=True
    ):
        if form == "10-Q" and document:
            html = client.get_filing_document(cik, accession, document)
            CORPUS.mkdir(parents=True, exist_ok=True)
            path.write_text(html, encoding="utf-8")
            return html
    return None


def count(texts: list[str]) -> list[str]:
    """Words most often lower case mid-sentence, in enough of ``texts``."""
    lower_docs = Counter[str]()
    lower = Counter[str]()
    capital = Counter[str]()
    for text in texts:
        seen: set[str] = set()
        for line in text.splitlines():
            for match in _WORD.finditer(line):
                word = match.group(0)
                before = line[: match.start()]
                if not before.strip() or _SENTENCE_END.search(before) or word.isupper():
                    continue
                key = word.casefold()
                if word.islower():
                    lower[key] += 1
                    seen.add(key)
                elif word[0].isupper() and word[1:].islower():
                    capital[key] += 1
        lower_docs.update(seen)
    floor = max(2, int(len(texts) * MIN_SHARE))
    return sorted(
        word
        for word, documents in lower_docs.items()
        if documents >= floor and lower[word] >= MIN_LOWER_SHARE * (lower[word] + capital[word])
    )


def main(size: int) -> None:
    client = SECClient(get_settings())
    texts: list[str] = []
    try:
        for company in _sample(size):
            try:
                html = _fetch(client, company["cik"])
            except Exception as error:  # noqa: BLE001 - a filer without a usable 10-Q is skipped
                print(f"skip {company['ticker']}: {error}")
                continue
            if html is not None:
                texts.append(html_to_text(html))
    finally:
        client.close()
    words = count(texts)
    OUT.write_text("\n".join(words) + "\n", encoding="utf-8")
    print(f"{len(words)} everyday words from {len(texts)} filings -> {OUT}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sample", type=int, default=250)
    main(parser.parse_args().sample)
