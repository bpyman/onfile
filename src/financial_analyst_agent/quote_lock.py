"""The quote lock: a model may quote the filing only word for word (ADR 0017, phase B).

``quotes_outside`` lists the passages a text puts in double quotation marks, straight
or curly, that are not verbatim in any of its sources. The comparison forgives two
things only, since neither changes what was said: runs of whitespace (a line break,
a hard space) and the shape of quotation marks and apostrophes. Case, punctuation and
word forms count, and a quotation of one word is checked like a longer one. Text
outside quotation marks is not checked here; the numeral lock holds its figures.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

__all__ = ["quotes_outside"]

_DOUBLE_QUOTES = "\"“”„‟"
# A quotation runs from one double quotation mark to the next; one left open runs
# to the end of the text, so an unclosed quotation is still checked.
_QUOTATION = re.compile(f"[{_DOUBLE_QUOTES}]([^{_DOUBLE_QUOTES}]*)(?:[{_DOUBLE_QUOTES}]|$)")
_QUOTE_SHAPES = str.maketrans(
    {
        **dict.fromkeys(_DOUBLE_QUOTES, '"'),
        **dict.fromkeys("‘’‚‛", "'"),
    }
)
_WHITESPACE = re.compile(r"\s+")


def _normal(text: str) -> str:
    return _WHITESPACE.sub(" ", text.translate(_QUOTE_SHAPES)).strip()


def quotes_outside(text: str, sources: Iterable[str]) -> list[str]:
    """Every quoted passage in ``text`` that no source holds verbatim, in order, once each."""
    held = [_normal(source) for source in sources]
    outside: list[str] = []
    for match in _QUOTATION.finditer(text):
        passage = match.group(1).strip()
        if not passage:
            continue
        wanted = _normal(passage)
        if not any(wanted in source for source in held) and passage not in outside:
            outside.append(passage)
    return outside
