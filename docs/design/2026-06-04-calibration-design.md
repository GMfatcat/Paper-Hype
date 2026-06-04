# Design Spec — Calibration & published false-positive rate（補洞 B）

- **Date:** 2026-06-04
- **Status:** Design approved; pending implementation plan
- **Part of:** "borrow & patch" item **B** (after A/GROBID). Patches the vs-market hard truth: competitors publish accuracy/FP numbers (CiteAudit 97%, GPT-5 checker ~17% FP); we publish none.
- **Affects:** new `skill/eval/` (+ a calibration doc + a README line). No change to `paper-verify`/`pdf-extract` logic — this measures them.
- **One-line:** A reproducible evaluation harness + a self-built labeled dataset that measures C1 (hallucinated-reference detection: FP / recall / precision) and C4 (retraction detection: precision / recall), and publishes the **measured** numbers with full dataset description and limitations.

---

## 1. Problem & goal

The competitive review found our biggest credibility gap: no published error rates. Now that #1 (paper-verify), #2 (pdf-extract), and A (GROBID refs) are done, calibrate the *fixed* system on a labeled set and publish honest numbers.

**Goal:** measurable, reproducible precision/recall/FP for the two deterministic checks that have ground truth — C1 (ref hallucination via `paper-verify --refs`) and C4 (retraction via `paper-verify` `is_retracted`) — published in the README + a calibration report.

**Honesty rules (binding):** publish only numbers actually produced by a run; describe the dataset and its limitations plainly; if a number is bad, publish it anyway. The 0–100 trust-risk **band has no ground truth → no number is claimed for it**.

**Non-goals:** calibrating the 0–100 bands; `author_identity_weak` (labels too subjective); changing any detection algorithm (B only measures + publishes; a bad result motivates a *separate* fix).

## 2. Self-built labeled datasets (committed, reproducible)

Stored in `repo/eval/datasets/`.

**C1 — `c1_references.jsonl`** (one JSON object per line: `{"ref": "<string>", "label": "real"|"fake"}`):
- **real** (~200–400): real bibliography entries pulled from ~10–15 real papers via GROBID, each **confirmed to exist via Crossref** before inclusion (so "real" is ground-truth).
- **fake** (~100–150): two kinds, both clearly synthetic:
  - *LLM-fabricated*: plausible title+authors+venue+year that resolve to nothing (mimics AI-hallucinated citations).
  - *perturbed-real*: a real ref with title/authors mutated so it no longer matches any record (hard fake).
- A header/README states these fakes are **synthetic test data**, not accusations about anyone.

**C4 — `c4_papers.jsonl`** (`{"doi": "<doi>", "label": "retracted"|"clean"}`):
- **retracted** (~30): DOIs sampled from the Retraction Watch dataset (available via Crossref).
- **clean** (~30): well-known non-retracted papers.

`build_dataset.py` documents/automates construction so the set can be regenerated/extended.

## 3. Evaluation harness (`repo/eval/`, reproducible)

- **`metrics.py`** (pure): `confusion(preds, labels, positive_label)` → counts; `precision_recall_fp(...)` → precision, recall, false_positive_rate. Unit-tested with synthetic preds/labels (no network).
- **`eval_c1.py`**: load `c1_references.jsonl`; for each ref call the same path `paper-verify` uses (`resolve_refs` → Crossref `query.bibliographic` + `match_reference`); predict `real` if resolved else `fake`; compute vs labels → **FP rate** (real refs wrongly called fake/unresolved), **recall** (fakes correctly caught), **precision**. Treat "fake/unresolved" as the positive class for recall.
- **`eval_c4.py`**: load `c4_papers.jsonl`; for each DOI call `paper-verify`'s `fetch_openalex`→`is_retracted`; predict retracted/clean; compute precision/recall/FP (positive = retracted).
- Both write a metrics JSON + a human-readable summary; **re-runnable** so numbers can be refreshed when the system changes. They hit live APIs (OpenAlex/Crossref) → integration-class; run once to produce the report.
- Import `paper-verify`'s functions directly (add `skill/paper-verify` to path) — reuse, don't reimplement.

## 4. Output / publish

- **`docs/calibration-2026-06.md`**: methodology; dataset description (sizes, construction, the fake-ref caveat); C1 numbers (precision/recall/FP); C4 numbers (precision/recall); **limitations** — small self-built set (numbers are indicative, not authoritative); fakes are LLM-hallucination-style, **not** adversarial paper-mill forgeries; C4 effectively measures **OpenAlex retraction coverage**, not our own cleverness.
- **README**: one measured line, e.g. `Measured on a self-built set (N real + M fake refs): C1 false-positive ≈ X%, recall ≈ Y%; C4 (K retracted + K clean): precision ≈ …, recall ≈ … — see docs/calibration-2026-06.md`. With the dataset-size + indicative caveat inline.
- Numbers are filled **after** the run; whatever comes out is what we publish.

## 5. Components / files

- **Create:** `repo/eval/{metrics.py, eval_c1.py, eval_c4.py, build_dataset.py, README.md, test_metrics.py}`, `repo/eval/datasets/{c1_references.jsonl, c4_papers.jsonl}`.
- **Create:** `repo/docs/calibration-2026-06.md`.
- **Modify:** `repo/README.md` (one measured line + link).
- **No change:** `paper-verify`, `pdf-extract` (measured, not modified). If C1 numbers reveal the `match_reference` 0.6 threshold is badly tuned, that is logged as a finding for a **separate** follow-up, not changed here.

## 6. Testing

- **Unit (no network):** `metrics.py` — feed synthetic `(preds, labels)` → assert precision/recall/FP correct (incl. edge cases: all-correct, all-wrong, empty). This is the hard gate.
- **Dataset sanity (no network):** the committed `.jsonl` files parse, have both labels, and meet minimum counts.
- **Integration (live APIs):** run `eval_c1.py` / `eval_c4.py` end-to-end to produce the actual metrics → fill the report + README. (This is the deliverable run, not a pass/fail assertion — but eval_c1 on the *fake* subset should show non-zero recall, and on a few obviously-real refs should resolve, as a smoke.)

## 7. Honesty risk points (call out in the report)

- Self-built set is small → label numbers "indicative, N=…", not authoritative.
- Fakes are LLM-fabricated/perturbed → represent AI-hallucination-style bad refs, not sophisticated paper-mill forgeries; real-world adversarial FP/recall may differ.
- C4 measures OpenAlex's retraction flag coverage + freshness (a very new retraction may be unflagged) — stated as such.
- Crossref `query.bibliographic` ranking + `match_reference` token threshold drive C1; the measured FP rate is a property of that pipeline, reproducible via the harness.

## 8. Rollout

Build harness + dataset in repo; `metrics.py` unit tests are the gate (no network). Run the integration evals once to produce real numbers; write `docs/calibration-2026-06.md` and the README line from those numbers. Local commits (no push until asked). Optional later: also run against CiteAudit's public benchmark for cross-comparability.
