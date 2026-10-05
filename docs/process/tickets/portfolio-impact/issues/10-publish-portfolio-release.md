# 10 — Publish the portfolio release

**What to build:** The public project looks finished: screenshots, a short GIF or recording, social preview, hosted demo link, evaluation numbers, and copy a recruiter can scan. A follow-up LinkedIn post can point at the live product rather than a local clone.

**Blocked by:** 01 — Reframe the portfolio storefront; 06 — Deploy the guarded public demo; 07 — Publish an evaluation and operability scorecard; 09 — Complete the flagship filing-change workflow.

**Status:** resolved

- [x] README shows a hosted demo link, a 30–60 second visual, two screenshots (multi-quarter comparison and exact filing provenance), architecture at a glance, evaluation results, setup, and honest limitations.
- [x] GitHub social preview uses a still from the demo.
- [x] A clip exists: one-click comparison, a follow-up that extends the analysis spec, a chart, then click-through to exact SEC evidence.
- [x] LinkedIn-ready copy is written from the finished storefront, not from the original brief's framing.

## Answer

README Try-it has the hosted URL, a looping GIF, two stills, and a walkthrough mp4. Scorecard copy is **9/9**. LinkedIn draft is [`docs/portfolio/release.md`](../../../../portfolio/release.md). GitHub social preview is uploaded.

- [`docs/portfolio/images/demo-walkthrough.gif`](../../../../portfolio/images/demo-walkthrough.gif)
- [`docs/portfolio/images/demo-walkthrough.mp4`](../../../../portfolio/images/demo-walkthrough.mp4) — Compare four quarters → `add Apple` → two-series chart → inspect Apple 10-Q
- [`docs/portfolio/images/compare-four-quarters.png`](../../../../portfolio/images/compare-four-quarters.png)
- [`docs/portfolio/images/inspect-exact-source.png`](../../../../portfolio/images/inspect-exact-source.png)
- [`docs/portfolio/images/social-preview.png`](../../../../portfolio/images/social-preview.png) (1280×640)

The mp4 was recorded against the fixture demo at this commit (~27s). Apple fills overlapping 10-Q cells; 2024-09-30 stays `missing_fact`.

## Comments

- Agent: do not fake a hosted URL. After Streamlit Cloud is live, capture the clip and stills listed in the release doc.
- Agent: captured live-demo stills and GIF; social preview still needs a Settings upload.
- Human: uploaded `docs/portfolio/images/social-preview.png` in GitHub Settings → Social preview.
- Agent: recorded `docs/portfolio/images/demo-walkthrough.mp4` from the fixture demo (compare → add Apple → inspect).
