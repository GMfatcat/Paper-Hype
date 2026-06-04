# Design Spec — C1 reference-verification quality improvement

- **Date:** 2026-06-04
- **Status:** Design approved; pending implementation plan
- **Motivation:** Calibration (2026-06) measured C1 at **FP ≈ 21%** (real refs wrongly called unresolved) and **recall ≈ 26%** — but the recall number was invalidated by too-easy perturbed fakes. This is the first change that *improves* `paper-verify`'s algorithm (prior work only measured it).
- **Affects:** `skill/paper-verify/verify.py` (+ live sync); `repo/eval/` (new hard-fake dataset + re-run); calibration report + README.
- **One-line:** Lower C1 false positives via **DOI-when-present** direct resolution + **top-N candidate matching with year corroboration** for no-DOI refs, and measure recall honestly against **fully-fabricated** fakes — publishing before/after numbers.

---

## 1. Problem & goal

`resolve_refs` currently resolves each reference by taking Crossref `query.bibliographic`'s **top-1** result and accepting if `match_reference` (title-token overlap ≥ 0.6) passes. Two failure modes drive the 21% FP: (a) the correct paper isn't ranked #1 (ranking noise) → rejected though real; (b) short titles tip below 0.6. And recall is unmeasurable with perturbed fakes that still match their source paper.

**Goal:** reduce C1 FP without tanking recall, and measure recall fairly with hard fakes. **Honesty:** publish before/after numbers as-measured; do not tune thresholds to hit a target (if tuned, log why).

**Non-goals:** other modes; ML-based matching (keep rule/token); changing C2–C5; the 0–100 band.

## 2. `verify.py` changes

1. **`extract_doi(ref)`** (pure): regex `10\.\d{4,}/[^\s"<>]+`, strip trailing punctuation (`.`,`,`,`)`,`;`). Returns the DOI or `None`.
2. **`_doi_exists(doi, timeout=30)`** (network): Crossref `GET /works/{doi}` → `True` if HTTP 200, `False` on 404, `None` on other error (caller treats `None` as "could not check" → falls through to title matching, never a hard "fake").
3. **`_search_reference_candidates(ref, rows=5, timeout=30)`** (network): Crossref `query.bibliographic` `rows=5` → list of `{title, year}` for the top candidates (replaces the single-title `_search_reference_title`).
4. **`match_any(ref, candidates)`** (pure): for each candidate compute title↔ref token overlap; accept if any candidate clears the bar:
   - base: `|title_tokens ∩ ref_tokens| / |title_tokens| ≥ 0.6` (current rule, per candidate);
   - short-title guard: if the title has ≤ 4 tokens, require all-but-one present;
   - year corroboration: if the ref contains a 4-digit year AND a candidate's year matches, the overlap bar for that candidate is relaxed to ≥ 0.5.
   Returns `True` if any candidate matches.
5. **`resolve_refs(refs, ...)`** new per-ref flow (interface unchanged — still returns `{provided_checked, provided_unresolved}`):
   - `doi = extract_doi(ref)`; if `doi` and `_doi_exists(doi) is True` → **resolved** (definitive).
   - else → `match_any(ref, _search_reference_candidates(ref))` → resolved/unresolved.
   - keep dependency-injection seams so unit tests need no network (inject a fake candidate-fetcher / doi-checker).
6. Keep `match_reference` (single-pair) as a helper used inside `match_any`; keep `_search_reference_title` only if still referenced, else remove. Thresholds (0.6 / 0.5 / short-title) are constants; may be **calibration-tuned once**, with the reason recorded — never tuned just to flatter a number.

## 3. Hard-fake dataset (fair recall)

- **`repo/eval/datasets/c1_references_hard.jsonl`**: same 128 **real** refs (label `real`) + **~100 fully-fabricated** refs (label `fake`): realistic-looking but entirely invented `title + authors + year`, **no DOI**, deliberately not corresponding to any real paper. Generated and committed by the implementer, with a header note marking them synthetic.
  - Optional mix: a few "real authors + fabricated title" hard cases (the trickiest kind).
- Keep the existing `c1_references.jsonl` (perturbed fakes) for an easy-vs-hard comparison.

## 4. Re-measurement

`eval_c1.py` is unchanged (already takes a dataset path). Run the 2×2:
- before (current verify.py): `c1_references.jsonl` (easy) — already have FP21/recall26.
- after (new verify.py): `c1_references.jsonl` (easy) and `c1_references_hard.jsonl` (hard).
Report: FP change on the real refs; recall on hard fakes (the fair number). Update `results-2026-06.json`.

## 5. Testing (TDD)

- **Pure unit (no network):**
  - `extract_doi`: strings with a DOI (mid-text, with trailing period, in a URL) → extracts; strings without → `None`.
  - `match_any`: candidate list where the right paper is at rank 3 → matches; short-title all-but-one; year-corroborated 0.5 case; all-wrong candidates → no match.
- **resolve_refs with injected fakes (no network):** DOI-present + doi_exists→True ⇒ resolved; DOI-present + doi_exists→False ⇒ unresolved; no-DOI + matching candidate ⇒ resolved; no-DOI + no match ⇒ unresolved.
- **Regression:** existing paper-verify unit suite (21+) still passes.
- **Integration (live):** the 2×2 re-measurement run (produces numbers, not pass/fail) — but sanity: hard fakes recall should be clearly higher than 26%, and real-ref FP should drop vs 21%.

## 6. Publish

- Update `repo/docs/calibration-2026-06.md`: add a **"C1 improvement (before → after)"** table — easy-fake FP/recall before vs after, plus hard-fake recall (the fair value). Keep all prior honest caveats.
- Update the README Calibration line to the improved numbers (with the hard-fake recall + new FP), still labelled indicative/N.
- If a number didn't improve as hoped, say so plainly.

## 7. Components / files

- **Modify:** `skill/paper-verify/verify.py`, `skill/paper-verify/test_verify.py` (+ sync verify.py to live `~/.claude/skills/.../paper-verify/`).
- **Create:** `repo/eval/datasets/c1_references_hard.jsonl`.
- **Modify:** `repo/eval/results-2026-06.json`, `repo/docs/calibration-2026-06.md`, `repo/README.md`.
- **No change:** pdf-extract, other modes, eval harness scripts (eval_c1.py reused as-is).

## 8. Honesty risk points

- Thresholds are tuned at most once, with reasons logged; numbers are re-measured, not hand-set.
- Hard fakes are LLM-fabricated → represent AI-hallucination-style fakes (the real C1 threat), still not adversarial paper-mill forgeries; stated.
- Even improved, C1 stays an **advisory** signal (DOI-direct is solid; no-DOI title matching remains probabilistic); the skill's "refs_unresolved is advisory, not decisive" stance is unchanged.
