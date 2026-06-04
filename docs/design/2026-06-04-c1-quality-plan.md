# C1 reference-verification quality — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lower C1 false positives (DOI-when-present direct resolution + top-N candidate matching with year corroboration) and measure recall honestly against fully-fabricated fakes, publishing before→after numbers.

**Architecture:** Augment `skill/paper-verify/verify.py`. New pure helpers (`extract_doi`, `_ref_year`, `_overlap`, `match_any`, `_parse_candidates`) + network seams (`_doi_exists`, `_search_reference_candidates`); `resolve_refs` gets a new DOI-first → top-N-match flow (same return shape; injectable `doi_checker`/`candidate_fetcher` seams). Pure helpers are the TDD gate (no network). Sequence: build hard fakes → snapshot BEFORE → change verify.py → snapshot AFTER → publish.

**Tech Stack:** Python 3.11 stdlib (`re`, `json`, `urllib`); pytest; reuses `repo/eval/eval_c1.py`.

**Spec:** `docs/design/2026-06-04-c1-quality-design.md`

**Honesty:** numbers re-measured, published as-is; thresholds tuned at most once with reason logged; C1 stays an advisory signal.

**Existing file:** `skill/paper-verify/verify.py` already has build_openalex_url, extract_facts, compute_flags, http_get_json, fetch_openalex, fetch_orcid_exists, enrich_authors, verify, **match_reference**, **_search_reference_title**, **resolve_refs(refs, searcher=None)**, format_output, CLI. Read it first. `re`, `json`, `urllib.parse/request` already imported.

---

## File Structure
| File | Change |
|---|---|
| `repo/eval/datasets/c1_references_hard.jsonl` | NEW: 128 real (reused) + ~100 fully-fabricated fakes |
| `skill/paper-verify/verify.py` | add DOI + top-N + match_any; rewrite resolve_refs flow |
| `skill/paper-verify/test_verify.py` | add pure tests; update test_resolve_refs to new seams |
| `repo/eval/results-2026-06.json` | add before/after × easy/hard C1 numbers |
| `repo/docs/calibration-2026-06.md` | add C1 before→after table |
| `repo/README.md` | update Calibration line |

---

## Task 1: Hard-fake dataset

**Files:** Create `repo/eval/datasets/c1_references_hard.jsonl`

- [ ] **Step 1: Reuse the 128 real refs + generate ~100 fully-fabricated fakes**
- Copy the `"label":"real"` lines from `repo/eval/datasets/c1_references.jsonl` into the new file unchanged.
- Generate **~100 fully-fabricated** reference strings: realistic-looking but entirely invented — plausible author surnames + a made-up paper title + a year (2015–2024), **no DOI**, spanning varied fields (ML, biology, physics, economics, medicine). They must NOT correspond to any real paper (invent distinctive titles, e.g. "Hierarchical Spectral Gating for Low-Resource Morphological Inflection"). Write each as `{"ref": "<authors>. <title>. <venue?> <year>.", "label": "fake"}`.
- Prepend a first line comment is not valid JSONL — instead document the synthetic nature in `repo/eval/README.md` (note these are LLM-fabricated test fakes, not real accusations).

- [ ] **Step 2: Sanity**
```bash
cd /d/paper/hype_experiment_3/repo/eval
python -c "import json;rows=[json.loads(l) for l in open('datasets/c1_references_hard.jsonl',encoding='utf-8') if l.strip()];import collections;print(collections.Counter(r['label'] for r in rows))"
```
Expected: both labels present, ~128 real + ~100 fake.

- [ ] **Step 3: Commit**
```bash
cd /d/paper/hype_experiment_3/repo
git add eval/datasets/c1_references_hard.jsonl
git commit -m "feat(eval): hard fully-fabricated C1 fake-reference dataset"
```

---

## Task 2: BEFORE snapshot (current verify.py)

**Files:** none (records numbers)

- [ ] **Step 1: Run eval_c1 on easy + hard with the CURRENT verify.py**
```bash
cd /d/paper/hype_experiment_3/repo/eval
echo "BEFORE easy:"; python eval_c1.py datasets/c1_references.jsonl
echo "BEFORE hard:"; python eval_c1.py datasets/c1_references_hard.jsonl
```
Record both metric blocks (precision/recall/false_positive_rate/n). The easy one should ≈ the prior FP 0.21 / recall 0.26. The hard one shows the current system's recall on fair fakes (likely higher — confirming recall-26 was a dataset artifact). Save these as `before_easy` / `before_hard` for Task 5 (note them in the commit message).

- [ ] **Step 2: Commit the note**
```bash
cd /d/paper/hype_experiment_3/repo
git commit --allow-empty -m "test(eval): C1 BEFORE snapshot — easy(FP/recall) + hard(recall) [numbers in body]"
```
(Put the actual numbers in the commit body.)

---

## Task 3: verify.py improvements (TDD)

**Files:** Modify `skill/paper-verify/verify.py`, `skill/paper-verify/test_verify.py`

- [ ] **Step 1: Failing pure tests** (add to test_verify.py)
```python
def test_extract_doi():
    assert verify.extract_doi("Foo. Bar. 2020. https://doi.org/10.1145/3292500.3330701") == "10.1145/3292500.3330701"
    assert verify.extract_doi("A paper, doi:10.1038/s41586-021-03819-2.") == "10.1038/s41586-021-03819-2"
    assert verify.extract_doi("No doi here, just text 2019") is None

def test_ref_year():
    assert verify._ref_year("Smith et al. Title. 2021.") == "2021"
    assert verify._ref_year("no year") is None

def test_match_any_rank3():
    ref = "Vaswani et al. Attention Is All You Need. 2017."
    cands = [{"title": "Wrong One", "year": "2019"},
             {"title": "Another Wrong", "year": "2018"},
             {"title": "Attention Is All You Need", "year": "2017"}]
    assert verify.match_any(ref, cands) is True

def test_match_any_year_relaxes():
    ref = "Doe. Deep Nets. 2020."   # title overlap ~0.5 with candidate
    cands = [{"title": "Deep Nets Revisited", "year": "2020"}]  # 2/3 title tokens, year matches -> relaxed bar 0.5
    assert verify.match_any(ref, cands) is True

def test_match_any_short_title_all_but_one():
    ref = "X. BERT pretraining. 2019."
    cands = [{"title": "BERT", "year": "2019"}]   # 1-token title present
    assert verify.match_any(ref, cands) is True

def test_match_any_all_wrong_no_match():
    ref = "Totally unique fabricated title about quokkas 2099"
    cands = [{"title": "Something unrelated", "year": "2001"}]
    assert verify.match_any(ref, cands) is False

def test_parse_candidates():
    data = {"message": {"items": [
        {"title": ["A Real Title"], "issued": {"date-parts": [[2017]]}},
        {"title": ["Second"], "issued": {"date-parts": [[None]]}}]}}
    out = verify._parse_candidates(data)
    assert out[0] == {"title": "A Real Title", "year": "2017"}
    assert out[1]["title"] == "Second" and out[1]["year"] is None
```

- [ ] **Step 2: Run, verify FAIL**

- [ ] **Step 3: Implement (append/adjust in verify.py)**
```python
_DOI_RE = re.compile(r'10\.\d{4,}/[^\s"<>]+')

def extract_doi(ref):
    if not ref:
        return None
    m = _DOI_RE.search(ref)
    return m.group(0).rstrip('.,;)]}>') if m else None

def _ref_year(ref):
    m = re.search(r'\b(19|20)\d{2}\b', ref or "")
    return m.group(0) if m else None

def _overlap(title, ref):
    tt = set(re.findall(r"\w+", (title or "").lower()))
    rt = set(re.findall(r"\w+", (ref or "").lower()))
    return (len(tt & rt) / len(tt)) if tt else 0.0

def match_any(ref, candidates):
    ry = _ref_year(ref)
    rt = set(re.findall(r"\w+", (ref or "").lower()))
    for c in candidates or []:
        title = c.get("title") or ""
        ttoks = re.findall(r"\w+", title.lower())
        n = len(ttoks)
        if 0 < n <= 4:                      # short-title guard
            present = len(set(ttoks) & rt)
            if present >= 1 and present >= n - 1:
                return True
            continue
        bar = 0.5 if (ry and c.get("year") and ry == c.get("year")) else 0.6
        if _overlap(title, ref) >= bar:
            return True
    return False

def _parse_candidates(data):
    out = []
    for it in ((data.get("message") or {}).get("items") or []):
        titles = it.get("title") or []
        if not titles:
            continue
        parts = ((it.get("issued") or {}).get("date-parts") or [[None]])
        year = str(parts[0][0]) if (parts and parts[0] and parts[0][0]) else None
        out.append({"title": titles[0], "year": year})
    return out

def _doi_exists(doi, timeout=30):
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi)}?mailto={MAILTO}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": f"paper-verify/1.0 (mailto:{MAILTO})"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return 200 <= r.status < 300
    except urllib.error.HTTPError as e:
        return False if e.code == 404 else None
    except Exception:
        return None

def _search_reference_candidates(ref, rows=5, timeout=30):
    q = urllib.parse.quote(ref[:400])
    url = f"https://api.crossref.org/works?query.bibliographic={q}&rows={rows}&mailto={MAILTO}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": f"paper-verify/1.0 (mailto:{MAILTO})",
                                                   "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return _parse_candidates(json.loads(r.read().decode("utf-8")))
    except Exception:
        return []
```
Add `import urllib.error` to the imports if not present (urllib.request implies it, but import explicitly for `urllib.error.HTTPError`).

- [ ] **Step 4: Rewrite `resolve_refs` (new flow + injectable seams)** — replace the existing `resolve_refs`:
```python
def resolve_refs(refs, candidate_fetcher=None, doi_checker=None):
    candidate_fetcher = candidate_fetcher or _search_reference_candidates
    doi_checker = doi_checker or _doi_exists
    unresolved = []
    for ref in refs:
        doi = extract_doi(ref)
        if doi:
            ex = doi_checker(doi)
            if ex is True:
                continue
            if ex is False:
                unresolved.append(ref); continue
            # ex is None -> couldn't check; fall through to title matching
        if match_any(ref, candidate_fetcher(ref)):
            continue
        unresolved.append(ref)
    return {"provided_checked": len(refs), "provided_unresolved": unresolved}
```

- [ ] **Step 5: Update the existing `test_resolve_refs`** (it used the old `searcher=` param) to the new seams:
```python
def test_resolve_refs(monkeypatch):
    # no-DOI refs: candidate_fetcher returns a matching candidate for the real one, nothing for the fake
    def fake_fetch(ref):
        return [{"title": "Attention Is All You Need", "year": "2017"}] if "Vaswani" in ref else []
    out = verify.resolve_refs(
        ["Vaswani Attention is all you need 2017",
         "Nonexistent fabricated reference xyz 2099"],
        candidate_fetcher=fake_fetch, doi_checker=lambda d: None)
    assert out["provided_checked"] == 2
    assert out["provided_unresolved"] == ["Nonexistent fabricated reference xyz 2099"]

def test_resolve_refs_doi_path(monkeypatch):
    out = verify.resolve_refs(
        ["Real. Title. 10.1038/s41586-021-03819-2.", "Fake. 10.9999/nope.doi.x 2099."],
        candidate_fetcher=lambda r: [],
        doi_checker=lambda d: d.startswith("10.1038"))
    assert out["provided_unresolved"] == ["Fake. 10.9999/nope.doi.x 2099."]
```
If `_search_reference_title` is now unused, leave it (harmless) or remove it and its test; keep `match_reference` + its test (still valid).

- [ ] **Step 6: Run full suite, verify PASS** — `cd /d/paper/hype_experiment_3/repo/skill/paper-verify && python -m pytest -m "not integration" -v` → all pass (new pure tests + updated resolve_refs tests + existing non-integration, no regression).

- [ ] **Step 7: Commit**
```bash
cd /d/paper/hype_experiment_3/repo
git add skill/paper-verify/verify.py skill/paper-verify/test_verify.py
git commit -m "feat(paper-verify): C1 DOI-direct + top-N candidate match (lower FP)"
```

---

## Task 4: AFTER snapshot (new verify.py)

**Files:** Modify `repo/eval/results-2026-06.json`

- [ ] **Step 1: Re-run eval_c1 on easy + hard with the NEW verify.py**
```bash
cd /d/paper/hype_experiment_3/repo/eval
echo "AFTER easy:"; python eval_c1.py datasets/c1_references.jsonl
echo "AFTER hard:"; python eval_c1.py datasets/c1_references_hard.jsonl
```
Record both. Expectation (record actual, don't force): AFTER-easy FP < 0.21 (DOI-direct + top-N reduce ranking-noise FPs); AFTER-hard recall high (fabricated fakes resolve to nothing). If FP didn't drop, report and note the likely cause.

- [ ] **Step 2: Update `results-2026-06.json`** — add a `c1_v2` object: `{"before_easy":{...}, "before_hard":{...}, "after_easy":{...}, "after_hard":{...}, "run_date":"2026-06-04"}` (from Task 2 + this task's numbers).

- [ ] **Step 3: Commit**
```bash
cd /d/paper/hype_experiment_3/repo
git add eval/results-2026-06.json
git commit -m "test(eval): C1 AFTER snapshot (easy FP drop + hard-fake recall)"
```

---

## Task 5: Publish + sync to live

**Files:** Modify `repo/docs/calibration-2026-06.md`, `repo/README.md`; sync `verify.py` to live

- [ ] **Step 1: Update `repo/docs/calibration-2026-06.md`** — add a "C1 improvement (before → after)" subsection with a table from the real numbers:
```markdown
### C1 improvement (2026-06): DOI-direct + top-N matching
| dataset | metric | before | after |
|---|---|---|---|
| easy fakes (perturbed) | false-positive (real refs) | [0.21] | [..] |
| easy fakes (perturbed) | recall (fakes) | [0.26] | [..] |
| hard fakes (fabricated) | recall (fakes) | [..] | [..] |
- Change: DOI-when-present resolves via Crossref `/works/{doi}` (definitive); no-DOI refs match against Crossref top-5 candidates with a short-title guard and year corroboration.
- Note: recall on *perturbed* fakes stays low **by construction** (they still contain the real title) — the honest recall number is on *fabricated* fakes. FP is the headline win.
- C1 remains an **advisory** signal.
```

- [ ] **Step 2: Update the README Calibration line** with the improved FP + hard-fake recall (keep indicative/N caveat).

- [ ] **Step 3: Sync verify.py to live**
```bash
cp /d/paper/hype_experiment_3/repo/skill/paper-verify/verify.py "/c/Users/GMfatcat/.claude/skills/dissecting-paper-hype/paper-verify/verify.py"
grep -c "def match_any\|def extract_doi" "/c/Users/GMfatcat/.claude/skills/dissecting-paper-hype/paper-verify/verify.py"
```
Expected: 2 (both new functions present in live).

- [ ] **Step 4: Commit**
```bash
cd /d/paper/hype_experiment_3/repo
git add docs/calibration-2026-06.md README.md
git commit -m "docs: publish C1 before→after numbers; sync verify.py to live"
git log --oneline -1 ; git status -sb | head -1
```

---

## Self-Review
- **Spec coverage:** §2.1 extract_doi→T3; §2.2 _doi_exists→T3; §2.3 _search_reference_candidates(+_parse_candidates)→T3; §2.4 match_any (short-title + year)→T3; §2.5 resolve_refs DOI-first flow→T3 (injectable seams, return shape unchanged); §3 hard fakes→T1; §4 re-measure 2×2→T2+T4; §5 testing (pure gate + injected resolve_refs + regression)→T3; §6 publish→T5; §7 files (verify.py + live sync, eval reused)→all.
- **Placeholder scan:** bracketed values in T5 table are fill-from-run (intentional). Fabricated refs in T1 are generated content (the implementer writes ~100 real synthetic strings), not a placeholder.
- **Consistency:** `extract_doi`, `_ref_year`, `_overlap`, `match_any`, `_parse_candidates`, `_doi_exists`, `_search_reference_candidates`, `resolve_refs(refs, candidate_fetcher, doi_checker)` names/signatures consistent across impl + tests; `match_reference` retained for its existing test; eval_c1 calls `resolve_refs(refs)` with defaults (unchanged behaviour). Return shape `{provided_checked, provided_unresolved}` unchanged so eval_c1/Mode C consume it as before.
- **Sequencing:** hard dataset (T1) + BEFORE (T2) precede the verify change (T3) so the before→after 2×2 is clean; AFTER (T4) then publish (T5). Pure tests in T3 are the gate; the eval runs are measurements.
