# eval/ — calibration harness

Measures C1 (hallucinated-reference detection), C4 (retraction), and `author_identity_weak` (FP focus) against committed labeled datasets. **Measure-only — no algorithm changes live here.**

Results feed `docs/calibration-2026-06.md`. Current numbers: 2026-06 run.

---

## Layout

```
eval/
  metrics.py              pure confusion matrix + precision/recall/FP (no network)
  test_metrics.py         unit tests for metrics (pytest, no network)
  build_dataset.py        (re)build self-built C1 from Crossref; attempt CiteAudit fetch
  eval_c1.py              run resolve_refs over C1 dataset -> metrics JSON
  eval_c4.py              run is_retracted over C4 dataset -> metrics JSON
  eval_author.py          run author_identity_weak over author dataset -> metrics JSON
  results-2026-06.json    raw output from the 2026-06 run (committed)
  datasets/
    c1_references.jsonl   {"ref": "...", "label": "real"|"fake"}  (n=200)
    c4_papers.jsonl       {"doi": "...", "label": "retracted"|"clean"}  (n=7)
    author_papers.jsonl   {"doi": "...", "label": "legit"|"suspicious"}  (n=5)
```

---

## Prerequisites

- Python 3.11+
- The `paper-verify` skill installed at `../skill/paper-verify/verify.py` (relative to this directory). The eval scripts import it directly via `sys.path.insert`.
- Live internet access — `eval_c1.py` hits **Crossref**, `eval_c4.py` and `eval_author.py` hit **OpenAlex**. Expect rate-limit delays; the scripts use the polite pool (`mailto=` param).

No additional pip packages beyond stdlib.

---

## Rebuilding the datasets

```bash
cd eval
python build_dataset.py
```

What it does:
1. Attempts to fetch the CiteAudit benchmark from a known URL. On 404 / network failure it prints a notice and continues — this is expected; self-built C1 is used instead.
2. Pulls reference lists for 5 real DOIs from Crossref and builds `datasets/c1_references.jsonl` (real refs + perturbed fakes).
3. `datasets/c4_papers.jsonl` and `datasets/author_papers.jsonl` are curated seed files — `build_dataset.py` does not overwrite them.

The committed datasets are the ones that produced the 2026-06 numbers. Rebuild only if you want a fresh sample or are adding entries.

---

## Running the evals

Each script prints a JSON object to stdout. Redirect to update `results-2026-06.json` if you re-run.

### C1 — reference resolution FP/recall

```bash
cd eval
# default: uses datasets/c1_references.jsonl (self-built, n=200)
python eval_c1.py

# or pass an explicit path (e.g., a CiteAudit file if available)
python eval_c1.py datasets/c1_references.jsonl
```

Sample sizes: up to 100 real + 100 fake (random.seed(0) for reproducibility). Hits Crossref in one batch call via `verify.resolve_refs`. Expect 30–120 seconds depending on API latency.

### C4 — retraction detection

```bash
cd eval
python eval_c4.py
```

Runs `verify.verify(doi)` for each of the 7 DOIs in `datasets/c4_papers.jsonl`. Hits OpenAlex. Expect ~30 seconds.

### author_identity_weak — FP on legit papers

```bash
cd eval
python eval_author.py
```

Runs `verify.verify(doi)` for each of the 5 DOIs in `datasets/author_papers.jsonl`. Hits OpenAlex. The primary reported number is the false-positive rate on legit papers — recall is n/a (no suspicious-labeled positives in the dataset).

---

## Unit tests (pure, no network)

```bash
cd eval
python -m pytest test_metrics.py -v
```

These test `metrics.py` only — no API calls. They are the hard gate: if they fail, the eval harness is broken.

---

## Notes on the numbers

- All metrics are point estimates with N stated. No confidence intervals (samples too small).
- C1 recall (~26%) is understated — see `docs/calibration-2026-06.md` for why the fake-construction method makes this a lower bound, not a fair measurement.
- C1 false-positive rate (~21%) is the honest cost of Crossref string matching; this is why `refs_unresolved` is advisory, never a decisive fraud flag.
- C4 100% recall/precision is on n=7 well-known retractions already indexed by OpenAlex; it is not a general retraction-detection rate.
- author FP 0% is on n=5 legit large-team papers; recall is n/a.

Full methodology and limitations: [docs/calibration-2026-06.md](../docs/calibration-2026-06.md).
