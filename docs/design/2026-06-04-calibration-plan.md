# Calibration & published FP rate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible eval harness + labeled datasets that measure C1 (hallucinated-reference detection), C4 (retraction), and `author_identity_weak` (FP-focused), then publish the **measured** numbers + limitations in a calibration report and the README.

**Architecture:** New `repo/eval/` (repo-level, NOT inside the installed skill). `metrics.py` is pure + unit-tested (the hard gate). `eval_c1/c4/author.py` import `paper-verify`'s functions and run them over committed JSONL datasets on **bounded samples**, hitting live OpenAlex/Crossref → metrics JSON + summary. Datasets are committed for reproducibility. No change to `paper-verify`/`pdf-extract` algorithms (measure only).

**Tech Stack:** Python 3.11 stdlib (`json`, `urllib`, `statistics`); pytest; reuses `skill/paper-verify/verify.py`.

**Spec:** `docs/design/2026-06-04-calibration-design.md` (incl. 2026-06-04 Addendum: no CIs; +author_identity_weak FP; CiteAudit-first for C1).

**Honesty (binding):** publish only numbers a run produced; if bad, publish anyway; point estimates with N (no confidence intervals); state every dataset's construction + limits. 0–100 band gets no number.

**Tractability notes:**
- Evals run on **samples** (default ≤100 real + ≤100 fake for C1; ≤20 for C4; ≤15 for author) to bound API calls; the report states the sample N.
- C1 "real" refs are pulled from **Crossref reference lists** of real DOIs (no GROBID needed for dataset building).
- CiteAudit benchmark fetch is **attempted**; on failure, self-built C1 set is used and the report says which ran.

---

## File Structure
| File | Responsibility |
|---|---|
| `repo/eval/metrics.py` | pure: confusion matrix, precision/recall/false-positive-rate |
| `repo/eval/test_metrics.py` | unit tests for metrics (no network) — **hard gate** |
| `repo/eval/datasets/c1_references.jsonl` | `{"ref","label":"real"\|"fake"}` (self-built C1) |
| `repo/eval/datasets/c4_papers.jsonl` | `{"doi","label":"retracted"\|"clean"}` |
| `repo/eval/datasets/author_papers.jsonl` | `{"doi","label":"legit"\|"suspicious"}` |
| `repo/eval/build_dataset.py` | (re)build self-built C1 from Crossref + perturbed fakes; attempt CiteAudit fetch |
| `repo/eval/eval_c1.py` | run resolve_refs over C1 set → metrics |
| `repo/eval/eval_c4.py` | run is_retracted over C4 set → metrics |
| `repo/eval/eval_author.py` | run author_identity_weak over author set → metrics |
| `repo/eval/README.md` | how to (re)build + run |
| `repo/docs/calibration-2026-06.md` | methodology + numbers + limitations |
| `repo/README.md` | one measured line + link |

`paper-verify` import shim (top of each eval_*.py):
```python
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skill", "paper-verify"))
import verify
```

---

## Task 1: `metrics.py` + tests (pure, hard gate)

**Files:** Create `repo/eval/metrics.py`, `repo/eval/test_metrics.py`

- [ ] **Step 1: Failing tests**
```python
# test_metrics.py
import metrics

def test_confusion_basic():
    preds  = ["fake","fake","real","real"]
    labels = ["fake","real","real","fake"]
    c = metrics.confusion(preds, labels, positive="fake")
    assert c == {"tp": 1, "fp": 1, "tn": 1, "fn": 1}

def test_prf_all_correct():
    m = metrics.precision_recall_fp(["fake","real"], ["fake","real"], positive="fake")
    assert m["precision"] == 1.0 and m["recall"] == 1.0 and m["false_positive_rate"] == 0.0

def test_prf_all_wrong():
    m = metrics.precision_recall_fp(["real","fake"], ["fake","real"], positive="fake")
    assert m["recall"] == 0.0 and m["false_positive_rate"] == 1.0

def test_prf_handles_zero_denominator():
    # no positives predicted, no positives present -> precision/recall defined as 1.0, fp 0.0
    m = metrics.precision_recall_fp(["real","real"], ["real","real"], positive="fake")
    assert m["false_positive_rate"] == 0.0
    assert m["n"] == 2

def test_prf_fp_rate_definition():
    # fp_rate = fp / (fp+tn): 1 real wrongly called fake out of 2 reals -> 0.5
    m = metrics.precision_recall_fp(["fake","real","real"], ["real","real","fake"], positive="fake")
    assert m["false_positive_rate"] == 0.5
```

- [ ] **Step 2: Run, verify FAIL** — `cd repo/eval && python -m pytest test_metrics.py -v`

- [ ] **Step 3: Implement**
```python
# metrics.py
def confusion(preds, labels, positive):
    tp = fp = tn = fn = 0
    for p, y in zip(preds, labels):
        if p == positive and y == positive: tp += 1
        elif p == positive and y != positive: fp += 1
        elif p != positive and y != positive: tn += 1
        else: fn += 1
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn}

def precision_recall_fp(preds, labels, positive):
    c = confusion(preds, labels, positive)
    tp, fp, tn, fn = c["tp"], c["fp"], c["tn"], c["fn"]
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    fp_rate = fp / (fp + tn) if (fp + tn) else 0.0
    return {"n": len(labels), "precision": round(precision, 4),
            "recall": round(recall, 4), "false_positive_rate": round(fp_rate, 4), **c}
```

- [ ] **Step 4: Run, verify PASS**

- [ ] **Step 5: Commit**
```bash
cd /d/paper/hype_experiment_3/repo
git add eval/metrics.py eval/test_metrics.py
git commit -m "feat(eval): pure metrics (confusion + precision/recall/fp)"
```

---

## Task 2: datasets + `build_dataset.py`

**Files:** Create `repo/eval/build_dataset.py`, `repo/eval/datasets/{c1_references.jsonl, c4_papers.jsonl, author_papers.jsonl}`

- [ ] **Step 1: Write `build_dataset.py`** — builds the self-built C1 set from Crossref reference lists + perturbed fakes, and attempts a CiteAudit fetch. (C4 + author are curated seed files written in Step 2.)
```python
# build_dataset.py  — run: python build_dataset.py
import json, os, re, urllib.parse, urllib.request

HERE = os.path.dirname(__file__)
DATADIR = os.path.join(HERE, "datasets")
MAILTO = "paper-verify@example.org"

# Real DOIs whose Crossref reference lists supply REAL refs (these papers exist & have refs in Crossref):
REAL_SOURCE_DOIS = [
    "10.1126/science.adi2336", "10.1038/s41586-021-03819-2",
    "10.1056/NEJMoa2034577", "10.1016/j.cell.2021.04.048",
    "10.1145/3442188.3445922",
]

def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": f"eval (mailto:{MAILTO})"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))

def real_refs_from_crossref(doi, limit=40):
    data = _get_json(f"https://api.crossref.org/works/{urllib.parse.quote(doi)}?mailto={MAILTO}")
    refs = []
    for r in (data.get("message", {}).get("reference") or [])[:limit]:
        title = r.get("article-title") or r.get("volume-title") or r.get("unstructured")
        author = r.get("author", "")
        year = r.get("year", "")
        s = " ".join(x for x in [author, title, year] if x).strip()
        if title and len(s) > 15:
            refs.append(s)
    return refs

def perturb(ref):
    # mutate a real ref into a non-existent one (swap title words, bump year)
    words = ref.split()
    words = ["Quantized" if w.istitle() else w for w in words][:1] + words[1:]
    ref2 = re.sub(r"\b(19|20)\d{2}\b", "2099", ref)
    return "Nonexistent Synthetic " + ref2  # clearly synthetic prefix

def build_c1():
    real, seen = [], set()
    for doi in REAL_SOURCE_DOIS:
        try:
            for s in real_refs_from_crossref(doi):
                if s not in seen:
                    seen.add(s); real.append(s)
        except Exception as e:
            print("skip", doi, e)
    fakes = [perturb(s) for s in real[:120]]  # perturbed-real fakes (clearly synthetic)
    rows = [{"ref": s, "label": "real"} for s in real] + [{"ref": s, "label": "fake"} for s in fakes]
    with open(os.path.join(DATADIR, "c1_references.jsonl"), "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"c1: {len(real)} real, {len(fakes)} fake")

def fetch_citeaudit():
    # best-effort: try known locations; on failure, note and skip
    candidates = [
        "https://raw.githubusercontent.com/checkcitation/citeaudit/main/benchmark.jsonl",
    ]
    for url in candidates:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "eval"})
            with urllib.request.urlopen(req, timeout=60) as r:
                open(os.path.join(DATADIR, "c1_citeaudit.jsonl"), "wb").write(r.read())
            print("CiteAudit fetched:", url); return True
        except Exception as e:
            print("CiteAudit fetch failed:", url, e)
    print("CiteAudit not fetched — using self-built C1 only")
    return False

if __name__ == "__main__":
    os.makedirs(DATADIR, exist_ok=True)
    fetch_citeaudit()
    build_c1()
```

- [ ] **Step 2: Write the curated seed datasets** — write `repo/eval/datasets/c4_papers.jsonl` (verifiable retracted + clean DOIs; expand toward ~15+15 by adding more from Retraction Watch search — keep only ones you confirm):
```
{"doi": "10.1016/S0140-6736(20)31180-6", "label": "retracted"}
{"doi": "10.1056/NEJMoa2007621", "label": "retracted"}
{"doi": "10.1016/j.surfin.2024.104081", "label": "retracted"}
{"doi": "10.1126/science.adi2336", "label": "clean"}
{"doi": "10.1038/s41586-021-03819-2", "label": "clean"}
{"doi": "10.48550/arXiv.2312.00752", "label": "clean"}
{"doi": "10.48550/arXiv.2305.10601", "label": "clean"}
```
and `repo/eval/datasets/author_papers.jsonl` (legit large-team papers that must NOT flag weak; suspicious best-effort):
```
{"doi": "10.48550/arXiv.2310.06825", "label": "legit"}
{"doi": "10.48550/arXiv.2307.09288", "label": "legit"}
{"doi": "10.48550/arXiv.2305.10601", "label": "legit"}
{"doi": "10.1038/s41586-021-03819-2", "label": "legit"}
{"doi": "10.1126/science.adi2336", "label": "legit"}
```
(During the run task you may add more confirmed entries; keep labels honest. `suspicious` entries are optional/best-effort — add only OpenAlex-resolved papers with genuinely weak author identity if you find any, else leave the suspicious recall as "n/a, no labeled positives".)

- [ ] **Step 3: Run the builder + sanity check**
```bash
cd /d/paper/hype_experiment_3/repo/eval
python build_dataset.py
wc -l datasets/c1_references.jsonl datasets/c4_papers.jsonl datasets/author_papers.jsonl
python -c "import json;[json.loads(l) for l in open('datasets/c1_references.jsonl',encoding='utf-8')];print('c1 parses')"
```
Expected: c1_references.jsonl has both labels and >50 lines; c4/author parse. If CiteAudit fetch failed, that's fine (noted).

- [ ] **Step 4: Commit**
```bash
cd /d/paper/hype_experiment_3/repo
git add eval/build_dataset.py eval/datasets/
git commit -m "feat(eval): dataset builder + curated C4/author + self-built C1"
```

---

## Task 3: eval scripts (predict mapping unit-tested; runs are integration)

**Files:** Create `repo/eval/eval_c1.py`, `repo/eval/eval_c4.py`, `repo/eval/eval_author.py`; add a small pure mapping + test to `test_metrics.py` (or a new `test_eval.py`)

- [ ] **Step 1: Failing unit test for the pure predict-mapping**
Add to `repo/eval/test_eval.py`:
```python
import eval_c1, eval_c4, eval_author

def test_c1_predict_from_unresolved():
    # resolve_refs returns provided_unresolved; a ref in that list => predicted "fake"
    assert eval_c1.predict("Ref A", {"provided_unresolved": ["Ref A"]}) == "fake"
    assert eval_c1.predict("Ref B", {"provided_unresolved": ["Ref A"]}) == "real"

def test_c4_predict_from_flag():
    assert eval_c4.predict({"flags": {"retracted": True}}) == "retracted"
    assert eval_c4.predict({"flags": {"retracted": False}}) == "clean"

def test_author_predict_from_flag():
    assert eval_author.predict({"flags": {"author_identity_weak": True}}) == "suspicious"
    assert eval_author.predict({"flags": {"author_identity_weak": False}}) == "legit"
```

- [ ] **Step 2: Run, verify FAIL**

- [ ] **Step 3: Implement the three eval scripts** (each: import shim + `predict()` pure helper + a `main()` that runs over the dataset on a bounded sample and prints metrics JSON). `eval_c1.py`:
```python
import os, sys, json, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skill", "paper-verify"))
import verify
sys.path.insert(0, os.path.dirname(__file__)); import metrics

HERE = os.path.dirname(__file__)

def predict(ref, resolve_result):
    return "fake" if ref in (resolve_result.get("provided_unresolved") or []) else "real"

def load(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]

def run(dataset_path, sample_per_label=100):
    rows = load(dataset_path)
    by = {"real": [r for r in rows if r["label"] == "real"],
          "fake": [r for r in rows if r["label"] == "fake"]}
    random.seed(0)
    sample = (random.sample(by["real"], min(sample_per_label, len(by["real"])))
              + random.sample(by["fake"], min(sample_per_label, len(by["fake"]))))
    refs = [r["ref"] for r in sample]
    rr = verify.resolve_refs(refs)              # one batch call to the real resolver
    preds = [predict(r["ref"], rr) for r in sample]
    labels = [r["label"] for r in sample]
    return metrics.precision_recall_fp(preds, labels, positive="fake")

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "datasets", "c1_references.jsonl")
    print(json.dumps({"dataset": os.path.basename(path), **run(path)}, ensure_ascii=False, indent=2))
```
`eval_c4.py`:
```python
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skill", "paper-verify"))
import verify
sys.path.insert(0, os.path.dirname(__file__)); import metrics
HERE = os.path.dirname(__file__)

def predict(result):
    return "retracted" if (result.get("flags") or {}).get("retracted") else "clean"

def run(path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    preds, labels = [], []
    for r in rows:
        res = verify.verify(r["doi"])
        preds.append(predict(res)); labels.append(r["label"])
    return metrics.precision_recall_fp(preds, labels, positive="retracted")

if __name__ == "__main__":
    path = os.path.join(HERE, "datasets", "c4_papers.jsonl")
    print(json.dumps({"dataset": "c4_papers.jsonl", **run(path)}, ensure_ascii=False, indent=2))
```
`eval_author.py`:
```python
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skill", "paper-verify"))
import verify
sys.path.insert(0, os.path.dirname(__file__)); import metrics
HERE = os.path.dirname(__file__)

def predict(result):
    return "suspicious" if (result.get("flags") or {}).get("author_identity_weak") else "legit"

def run(path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    preds, labels = [], []
    for r in rows:
        res = verify.verify(r["doi"])
        preds.append(predict(res)); labels.append(r["label"])
    m = metrics.precision_recall_fp(preds, labels, positive="suspicious")
    # primary number is FP rate on legit; also report how many legit total
    m["legit_n"] = sum(1 for l in labels if l == "legit")
    return m

if __name__ == "__main__":
    path = os.path.join(HERE, "datasets", "author_papers.jsonl")
    print(json.dumps({"dataset": "author_papers.jsonl", **run(path)}, ensure_ascii=False, indent=2))
```

- [ ] **Step 4: Run, verify the predict-mapping unit tests PASS** — `cd repo/eval && python -m pytest test_eval.py -v` (pure, no network).

- [ ] **Step 5: Commit**
```bash
cd /d/paper/hype_experiment_3/repo
git add eval/eval_c1.py eval/eval_c4.py eval/eval_author.py eval/test_eval.py
git commit -m "feat(eval): eval_c1/c4/author runners (predict mapping unit-tested)"
```

---

## Task 4: Run the evals (integration, live APIs) → capture numbers

**Files:** none (produces numbers; may write `repo/eval/results-2026-06.json`)

- [ ] **Step 1: Run all three evals** (live OpenAlex/Crossref; minutes)
```bash
cd /d/paper/hype_experiment_3/repo/eval
echo "== C1 (self-built; CiteAudit if datasets/c1_citeaudit.jsonl exists) =="
[ -f datasets/c1_citeaudit.jsonl ] && python eval_c1.py datasets/c1_citeaudit.jsonl
python eval_c1.py datasets/c1_references.jsonl
echo "== C4 =="; python eval_c4.py
echo "== author =="; python eval_author.py
```
Record the printed metrics JSON for each (precision / recall / false_positive_rate / n). Save the combined output to `repo/eval/results-2026-06.json`.

- [ ] **Step 2: Sanity of the run** — C1 on the self-built set should show meaningful separation (fakes mostly → unresolved = caught; reals mostly → resolved). C4: known retracted should be caught (recall high, depends on OpenAlex coverage). author: legit papers should mostly NOT be flagged (low FP). **Do not tune anything to hit a target — record what happens.** If a number is surprising, note the likely cause (e.g., Crossref ranking noise inflating C1 FP; OpenAlex missing a recent retraction).

- [ ] **Step 3: Commit the raw results**
```bash
cd /d/paper/hype_experiment_3/repo
git add eval/results-2026-06.json
git commit -m "test(eval): captured calibration run results (2026-06)"
```

---

## Task 5: Publish — calibration report + README line + eval README

**Files:** Create `repo/docs/calibration-2026-06.md`, `repo/eval/README.md`; Modify `repo/README.md`

- [ ] **Step 1: Write `repo/docs/calibration-2026-06.md`** from the Task-4 numbers. Structure (fill bracketed values from results-2026-06.json):
```markdown
# Calibration (2026-06)

Measured on a reproducible harness (`eval/`). Point estimates, with N. No confidence intervals.

## C1 — hallucinated-reference detection (paper-verify --refs)
- Dataset(s): [CiteAudit benchmark sample of N / self-built: R real + F fake refs (real = Crossref reference lists; fake = synthetic perturbed)].
- false-positive rate (real refs wrongly called unresolved): [X]%  (n=[..])
- recall (fake refs caught): [Y]%
- precision: [..]

## C4 — retraction detection (OpenAlex is_retracted)
- Dataset: [K] retracted + [K] clean (curated, verifiable).
- precision [..], recall [..], FP [..]
- Note: this primarily measures **OpenAlex retraction-flag coverage/freshness**, not our own logic.

## author_identity_weak (FP-focused)
- Dataset: [L] legit large-team papers (+ [S] suspicious, best-effort).
- **false-positive rate on legit papers: [Z]%** (the key number — large real teams must not be flagged).
- recall on suspicious: [indicative / n/a if no labeled positives].

## Limitations (honest)
- Self-built sets are small → numbers are indicative, not authoritative (N stated above).
- Fake refs are LLM/perturbation-style hallucinations, **not** adversarial paper-mill forgeries; real-world adversarial rates may differ.
- C4 = OpenAlex coverage; a very recent retraction may be unflagged.
- author-identity labels are partly subjective; the defensible number is the legit-paper FP rate.
- C1 FP/recall are properties of Crossref `query.bibliographic` + the `match_reference` token threshold; reproducible via `eval/`.
```

- [ ] **Step 2: Write `repo/eval/README.md`** — how to rebuild datasets (`python build_dataset.py`) and run (`python eval_c1.py [path]`, `eval_c4.py`, `eval_author.py`); note evals hit live APIs and run on samples; numbers feed `docs/calibration-2026-06.md`.

- [ ] **Step 3: Add the measured line to `repo/README.md`** — under a new "## Calibration" heading near the License/Acknowledgements area, one line with the actual numbers + caveat + link, e.g.:
`**Calibration (indicative, self-built set):** C1 hallucinated-ref false-positive ≈ [X]% / recall ≈ [Y]%; author-identity false-positive on legit large-team papers ≈ [Z]%; C4 retraction recall ≈ [..] (OpenAlex coverage). N and limits in [docs/calibration-2026-06.md](./docs/calibration-2026-06.md).`

- [ ] **Step 4: Commit**
```bash
cd /d/paper/hype_experiment_3/repo
git add docs/calibration-2026-06.md eval/README.md README.md
git commit -m "docs(eval): publish calibration numbers + limitations (2026-06)"
git log --oneline -1 ; git status -sb | head -1
```

---

## Self-Review
- **Spec coverage:** §1 goal/honesty/no-CI → header + metrics (point estimates) + Task 5 limitations; §2 datasets (C1 self-built via Crossref, C4, +Addendum author + CiteAudit-first) → Task 2 + eval_c1 CiteAudit-first in Task 4; §3 harness (metrics + eval_c1/c4/author, import paper-verify) → Tasks 1+3; §4 publish → Task 5; §5 components (repo/eval, no paper-verify change) → all; §6 testing (metrics unit gate + dataset sanity + integration runs) → Tasks 1/2/4; Addendum author FP + CiteAudit-first + no CIs → Tasks 2/3/4/5.
- **Placeholder scan:** bracketed values in Task 5 are **fill-from-run** outputs (intentional, not TODO). CiteAudit fetch URL is best-effort with explicit fallback. Dataset seed lists are concrete DOIs; "expand toward N" is optional enrichment, the seeds suffice to run.
- **Consistency:** `predict()` signatures match tests (eval_c1.predict(ref, result); eval_c4/author.predict(result)); `metrics.precision_recall_fp(preds, labels, positive=...)` used identically everywhere; positive classes — C1 "fake", C4 "retracted", author "suspicious" — consistent across scripts, tests, and report; import shim identical in all three eval scripts; reuses `verify.resolve_refs` / `verify.verify` (existing) without modification.
- **Hard gate vs run:** Tasks 1 + 3 unit tests (pure, no network) are the completion gate; Task 4 is the live measurement run (records whatever comes out); Task 5 publishes those numbers. No algorithm tuning to hit targets.
