# Calibration (2026-06)

Measured on a reproducible harness (`eval/`). Point estimates with N stated. No confidence intervals — samples are too small to make them meaningful.

Run date: 2026-06-04. Source file: `eval/results-2026-06.json`.

---

## C1 — hallucinated-reference detection (`paper-verify --refs`)

- **Dataset:** self-built — 100 real refs (from Crossref reference lists of 5 real DOIs) + 100 fake refs (perturbed from the same real refs: "Nonexistent Synthetic" prefix + year bumped to 2099). Total n=200.
- CiteAudit benchmark: attempted fetch → HTTP 404 — not available; self-built set used, as planned.

| Metric | Value | Raw counts |
|---|---|---|
| false-positive rate (real refs wrongly called unresolved) | **21.0%** | fp=21 / (fp+tn)=100 |
| recall (fake refs caught as unresolved) | **26.0%** | tp=26 / (tp+fn)=100 |
| precision | **55.3%** | tp=26 / (tp+fp)=47 |

### Honest interpretation of the C1 numbers

**False-positive rate ~21% — this is the signal that matters most for user trust.**
Roughly 1 in 5 real references is returned as "unresolved" by the Crossref `query.bibliographic` API + the `match_reference` 0.6 token-overlap threshold. This is not a bug being hidden — it is a known property of bibliographic string matching on a noisy ranking API. **This is exactly why the skill treats `refs_unresolved` as an ADVISORY signal, never a decisive fraud flag.** The calibration confirms that design choice: at 21% FP, any tool that declared "unresolved = fabricated" would produce unacceptable false accusations. The skill explicitly labels these as "could not be confirmed" rather than "fake."

**Recall ~26% — this number is understated by a dataset limitation and should NOT be read as the skill's true detection capability.**
The synthetic fakes were built by prepending "Nonexistent Synthetic" and bumping the year to 2099, but kept the rest of the original title tokens intact. Because the perturbed strings still share most real title words with the original paper, Crossref's `query.bibliographic` often matches the *original* real paper anyway, so the fake is resolved — correctly from Crossref's perspective, incorrectly from the eval's perspective. In other words, the fake-construction method was not adversarial enough: the Crossref resolver is robust to simple prefix+year perturbation when the core title tokens survive. A fair recall test requires **fully fabricated titles** — plausible-sounding paper titles that have never existed. This is logged as future work; the recall figure here is a lower bound of uncertain tightness, not a fair estimate. **We do not fix this here (calibration B = measure only, no algorithm changes).**

---

## C4 — retraction detection (OpenAlex `is_retracted`)

- **Dataset:** 3 retracted + 4 clean papers (curated, verifiable DOIs). Total n=7.

| Metric | Value |
|---|---|
| precision | 1.0 (3/3 retracted papers correctly flagged) |
| recall | 1.0 (0 retracted papers missed) |
| false-positive rate | 0.0 (0/4 clean papers wrongly flagged) |

### Honest interpretation of the C4 numbers

**100% precision and recall — but n=7 on well-known retractions.**
This does not mean the skill catches all retractions. It measures **OpenAlex retraction-flag coverage on a curated set of high-profile cases** — these are papers already documented in Retraction Watch and indexed in OpenAlex. The result tells us: for retractions that OpenAlex has already flagged, the `is_retracted` call works as expected. It says nothing about: (a) very recent retractions not yet in OpenAlex, (b) retractions in small journals with low OpenAlex coverage, or (c) expressions of concern not elevated to full retraction status. The n=7 figure is stated prominently so readers do not over-read the 100% numbers.

---

## `author_identity_weak` — false-positive focus

- **Dataset:** 5 legit large-team papers (papers with many OpenAlex-indexed authors, which must NOT be flagged weak). 0 suspicious-labeled positives (best-effort search found none meeting the labeling standard). Total n=5.

| Metric | Value |
|---|---|
| false-positive rate on legit papers | **0.0%** | fp=0 / 5 legit |
| recall on suspicious | n/a (no labeled positives in dataset) |

### Honest interpretation of the author numbers

**0% FP on legit papers (n=5)** — this validates an earlier fix: papers where OpenAlex returns an unknown or null `works_count` for some authors are no longer flagged as "identity weak." That specific regression is confirmed absent on these 5 papers. However, n=5 is small and all papers are from the same regime (large well-indexed teams). Recall is genuinely n/a — there were no suspicious-labeled positives to test against, because finding papers with objectively weak author identity that are also OpenAlex-indexed and reliably labelable proved intractable within this calibration scope.

---

## Limitations (honest)

- **Small self-built sets.** n=200 for C1, n=7 for C4, n=5 for author. These are indicative point estimates, not statistically tight rates. The stated N is part of every number.
- **C1 fakes are not adversarial.** The perturbation method (prefix + year bump) is easy — not representative of real paper-mill forgeries or LLM hallucinations that produce plausible but nonexistent titles. Real-world false-negative rates (missed fabrications) are unknown.
- **C4 = OpenAlex coverage, not detection logic.** The skill delegates entirely to OpenAlex's `is_retracted` field. Our contribution is routing the call and surfacing the flag — not building a retraction detector.
- **Author-identity labels are partly subjective.** The defensible number from this eval is the legit-paper FP rate, not recall.
- **C1 FP/recall are properties of Crossref `query.bibliographic` + the `match_reference` 0.6 token threshold**, not of any magic classifier. They are reproducible via `eval/eval_c1.py` on the committed dataset.
- **No confidence intervals.** With these sample sizes, a Wilson interval would be wide enough to be misleading about precision. Stating N and raw counts is more honest.

---

## Next steps from these numbers

1. **Build harder C1 fakes for a fair recall measurement.** Fully fabricated titles (no surviving real title tokens) are required. This is the single most important follow-up; until done, the 26% recall figure should not be cited as the skill's capability.
2. **Investigate cutting C1 FP.** Two approaches worth exploring as separate future work: (a) prefer DOI-based resolution over string matching when a DOI is present in the reference; (b) tighten (raise) the `match_reference` threshold or add a second-pass re-rank. Neither change is made here — calibration is measure-only.
3. **Expand C4 and author datasets** with confirmed entries from a broader venue/journal range to stress-test coverage rather than just known high-profile cases.
