from __future__ import annotations

import difflib
import operator
from collections.abc import Sequence
from dataclasses import FrozenInstanceError

import pytest

from financial_analyst_agent.issuer_index import IssuerIndex


def test_an_issuer_index_owns_read_only_maps() -> None:
    phrases = {"microsoft": "MSFT"}
    index = IssuerIndex(phrases=phrases)
    phrases["apple"] = "AAPL"

    assert "apple" not in index.phrases
    with pytest.raises(FrozenInstanceError):
        index.phrases = {}  # type: ignore[misc]
    for mapping in (
        index.phrases,
        index.tickers,
        index.display_names,
        index.ciks,
        index.shared,
    ):
        with pytest.raises(TypeError):
            operator.setitem(mapping, "new", "value")


def test_correction_reuses_one_candidate_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    index = IssuerIndex(phrases={"microsoft": "MSFT", "alphabet": "GOOGL"})
    candidate_collections: list[Sequence[str]] = []
    get_close_matches = difflib.get_close_matches

    def remember_candidates(
        word: str, possibilities: Sequence[str], n: int = 3, cutoff: float = 0.6
    ) -> list[str]:
        candidate_collections.append(possibilities)
        return get_close_matches(word, possibilities, n=n, cutoff=cutoff)

    monkeypatch.setattr(difflib, "get_close_matches", remember_candidates)

    assert [mention.query for mention in index.correct("microsft")] == ["MSFT"]
    assert [mention.query for mention in index.correct("microsft again")] == ["MSFT"]
    assert candidate_collections[0] is candidate_collections[1]
