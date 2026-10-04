# 03 — Keep each metric's label and unit in the catalog

**What to build:** Adding a metric is one catalog entry (ADR 0005, Consequences). The rules planner now reads metric phrases from the catalog, but a metric's display facts still live elsewhere: its label in `presentation._FIELD_LABELS`, and its value kind (USD, percent, multiple, per share) in `presentation.chart_value_kind`, which derives it from `MULTIPLE_FORMULAS` / `PERCENT_FORMULAS` / `PER_SHARE_METRICS` tuples in `contracts.py`. Move label and value kind onto the catalog entry so presentation reads them from one place, and derive the `contracts.py` tuples from the catalog (or retire them).

Found by the 2026-10-01 PRD/ADR review (Standards S4). The phrase-table half is done (`016dc59`).

Spec: ADR 0004 (phrase table), ADR 0005.

**Blocked by:** None — can start immediately

**Status:** done

## Answer

Each metric's label and kind of value (USD, percent, multiple, per share) is one entry in `services/metric_catalog.METRIC_DISPLAY`, covering every metric the window can show: the asked-for ones, formula inputs, and the parts of a derived figure. The presentation reads labels (`format_field_name`) and value kinds (`chart_value_kind`) from it; `_FIELD_LABELS` keeps only the table's own columns. `contracts.PERCENT_FORMULAS`, `MULTIPLE_FORMULAS` and `PER_SHARE_METRICS` are derived from it, as is the catalog's own per-share set, so the per-share list is no longer written twice. A test checks every metric has an entry. In passing, "amortization_of_intangibles" read "Amortization Of Intangibles" from the slug fallback; its entry says "Amortization of intangibles". Adding a metric still means its concepts or formula, its phrases, and this entry, all in the catalog except a formula's components in `contracts.FORMULA_COMPONENTS`.
