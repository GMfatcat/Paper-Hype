# C1 Second Resolver (OpenAlex) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** When Crossref fails to match a reference, retry against OpenAlex search-by-title before declaring it unresolved — cutting C1 false-positives without hurting recall (~0.82).

**Architecture:** Add `_search_reference_openalex(ref)` to `paper-verify/verify.py` and append one OpenAlex step (top-1 + strict `match_any`) to `resolve_refs`, firing only on a Crossref miss.

**Tech Stack:** Python 3 stdlib (`urllib`, `json`); pytest. Reuses `OPENALEX`, `MAILTO`, `http_get_json`, `match_any`, `_parse_candidates` patterns already in verify.py.

**Spec:** `docs/design/2026-06-05-c1-second-resolver-design.md`

**Conventions:** Work in `D:\paper\hype_experiment_3\repo`. Run pytest from `skill/paper-verify/`. Injectable-function unit tests = hard TDD gate (no network). Commit after each task; do NOT push. Commit trailer EXACTLY: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

## Task 1: `_search_reference_openalex` fetcher

**Files:**
- Modify: `skill/paper-verify/verify.py` (add after `_search_reference_candidates`)
- Test: `skill/paper-verify/test_verify.py`

- [ ] **Step 1: Write failing tests** (monkeypatch `http_get_json` — no network)

```python
def test_search_reference_openalex_parses(monkeypatch):
    monkeypatch.setattr(verify, "http_get_json", lambda url, timeout=30: {
        "results": [{"display_name": "A Real Title", "publication_year": 2017}]})
    out = verify._search_reference_openalex("some ref string")
    assert out == [{"title": "A Real Title", "year": "2017"}]

def test_search_reference_openalex_empty_on_error(monkeypatch):
    def boom(url, timeout=30):
        raise RuntimeError("network")
    monkeypatch.setattr(verify, "http_get_json", boom)
    assert verify._search_reference_openalex("x") == []

def test_search_reference_openalex_empty_results(monkeypatch):
    monkeypatch.setattr(verify, "http_get_json", lambda url, timeout=30: {"results": []})
    assert verify._search_reference_openalex("x") == []
```

- [ ] **Step 2: Run to verify fail**

Run: `cd skill/paper-verify && python -m pytest test_verify.py -k search_reference_openalex -v`
Expected: FAIL (`no attribute '_search_reference_openalex'`)

- [ ] **Step 3: Implement the fetcher**

Add to `verify.py` after `_search_reference_candidates`:

```python
def _search_reference_openalex(ref, timeout=30):
    # Second resolver: OpenAlex search-by-title for refs Crossref query.bibliographic missed.
    q = urllib.parse.quote((ref or "")[:400])
    url = f"{OPENALEX}/works?search={q}&per_page=1&mailto={MAILTO}"
    try:
        data = http_get_json(url, timeout=timeout)
    except Exception:
        return []
    out = []
    for w in (data.get("results") or []):
        title = w.get("display_name") or w.get("title")
        if not title:
            continue
        yr = w.get("publication_year")
        out.append({"title": title, "year": str(yr) if yr else None})
    return out
```

Note: `http_get_json`, `OPENALEX`, `MAILTO`, `urllib.parse` are already defined/imported in verify.py.

- [ ] **Step 4: Run to verify pass**

Run: `cd skill/paper-verify && python -m pytest test_verify.py -k search_reference_openalex -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
cd /d/paper/hype_experiment_3/repo
git add skill/paper-verify/verify.py skill/paper-verify/test_verify.py
git commit -m "feat(paper-verify): _search_reference_openalex second resolver fetcher

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Wire OpenAlex step into `resolve_refs`

**Files:**
- Modify: `skill/paper-verify/verify.py` (`resolve_refs`)
- Test: `skill/paper-verify/test_verify.py`

- [ ] **Step 1: Read current `resolve_refs`.** It is:

```python
def resolve_refs(refs, candidate_fetcher=None, doi_checker=None):
    candidate_fetcher = candidate_fetcher or _search_reference_candidates
    doi_checker = doi_checker or _doi_exists
    unresolved = []
    for ref in refs:
        doi = extract_doi(ref)
        if doi and doi_checker(doi) is True:
            continue
        if match_any(ref, (candidate_fetcher(ref) or [])[:1]):
            continue
        unresolved.append(ref)
    return {"provided_checked": len(refs), "provided_unresolved": unresolved}
```

- [ ] **Step 2: Write failing tests**

```python
def test_resolve_refs_openalex_rescues_crossref_miss():
    # Crossref returns nothing; OpenAlex returns the matching title -> resolved
    out = verify.resolve_refs(
        ["Vaswani et al. Attention Is All You Need. 2017."],
        candidate_fetcher=lambda r: [],
        doi_checker=lambda d: None,
        oa_fetcher=lambda r: [{"title": "Attention Is All You Need", "year": "2017"}])
    assert out["provided_unresolved"] == []

def test_resolve_refs_both_sources_miss_unresolved():
    out = verify.resolve_refs(
        ["Totally fabricated nonexistent title xyz 2099"],
        candidate_fetcher=lambda r: [],
        doi_checker=lambda d: None,
        oa_fetcher=lambda r: [{"title": "Some Unrelated Real Paper", "year": "2001"}])
    assert out["provided_unresolved"] == ["Totally fabricated nonexistent title xyz 2099"]

def test_resolve_refs_crossref_hit_skips_openalex():
    calls = {"oa": 0}
    def oa(r):
        calls["oa"] += 1
        return [{"title": "Attention Is All You Need", "year": "2017"}]
    out = verify.resolve_refs(
        ["Vaswani Attention Is All You Need 2017"],
        candidate_fetcher=lambda r: [{"title": "Attention Is All You Need", "year": "2017"}],
        doi_checker=lambda d: None,
        oa_fetcher=oa)
    assert out["provided_unresolved"] == []
    assert calls["oa"] == 0   # OpenAlex must NOT be consulted when Crossref already matched

def test_resolve_refs_doi_still_wins_first():
    calls = {"cr": 0, "oa": 0}
    def cr(r): calls["cr"] += 1; return []
    def oa(r): calls["oa"] += 1; return []
    out = verify.resolve_refs(
        ["Real. Title. 10.1038/s41586-021-03819-2."],
        candidate_fetcher=cr, doi_checker=lambda d: d.startswith("10.1038"), oa_fetcher=oa)
    assert out["provided_unresolved"] == []
    assert calls["cr"] == 0 and calls["oa"] == 0   # DOI-direct short-circuits both
```

- [ ] **Step 3: Run to verify fail**

Run: `cd skill/paper-verify && python -m pytest test_verify.py -k "openalex_rescues or both_sources_miss or crossref_hit_skips or doi_still_wins" -v`
Expected: FAIL (`resolve_refs() got an unexpected keyword argument 'oa_fetcher'`)

- [ ] **Step 4: Implement the change**

Replace `resolve_refs` with:

```python
def resolve_refs(refs, candidate_fetcher=None, doi_checker=None, oa_fetcher=None):
    candidate_fetcher = candidate_fetcher or _search_reference_candidates
    doi_checker = doi_checker or _doi_exists
    oa_fetcher = oa_fetcher or _search_reference_openalex
    unresolved = []
    for ref in refs:
        doi = extract_doi(ref)
        if doi and doi_checker(doi) is True:
            continue  # DOI confirmed to exist -> resolved
        if match_any(ref, (candidate_fetcher(ref) or [])[:1]):
            continue  # Crossref query.bibliographic top-1
        if match_any(ref, (oa_fetcher(ref) or [])[:1]):
            continue  # second resolver: OpenAlex search-by-title (only on Crossref miss)
        unresolved.append(ref)
    return {"provided_checked": len(refs), "provided_unresolved": unresolved}
```

- [ ] **Step 5: Run to verify pass**

Run: `cd skill/paper-verify && python -m pytest test_verify.py -k "openalex_rescues or both_sources_miss or crossref_hit_skips or doi_still_wins" -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Full suite — no regression**

Run: `cd skill/paper-verify && python -m pytest -m "not integration" -q`
Expected: all pass. The pre-existing `test_resolve_refs` / `test_resolve_refs_doi_path` must still pass (they don't pass `oa_fetcher`; the default would call real network — BUT those tests inject `candidate_fetcher` that matches or returns [], and for the ones that end unresolved the default `oa_fetcher` would hit network).

  **IMPORTANT:** check the two pre-existing tests. `test_resolve_refs` expects `["Nonexistent fabricated reference xyz 2099"]` unresolved with only `candidate_fetcher`/`doi_checker` injected — with the new default `oa_fetcher` it would now call real OpenAlex for that ref. To keep it deterministic and offline, ADD `oa_fetcher=lambda r: []` to those two existing test calls. Make that edit, then re-run. This is a test-only change preserving their intent (no real network in unit tests).

- [ ] **Step 7: Commit**

```bash
cd /d/paper/hype_experiment_3/repo
git add skill/paper-verify/verify.py skill/paper-verify/test_verify.py
git commit -m "feat(paper-verify): resolve_refs second resolver (OpenAlex on Crossref miss)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Re-measure (recall gate) + record + sync

**Files:**
- Run: `eval/eval_c1.py`, `eval/modec_c1_run.py`
- Modify: `eval/results-2026-06.json`, `docs/calibration-2026-06.md`
- Copy: `skill/paper-verify/verify.py` → live

> **Executor note:** `eval_c1.py` on the hard set is slow (~15–20 min, network). The CONTROLLER will run these evals in the background (subagent foreground bash caps out). If you are the controller, run Steps 1–2 as background commands and wait for completion before recording. If you are a subagent, report that the long evals must be run by the controller and do Steps 4–5 only after numbers are provided.

- [ ] **Step 1: Recall gate — hard set** (slow; background)

Run: `cd eval && python eval_c1.py datasets/c1_references_hard.jsonl`
Record recall + FP. **GATE:** recall must hold ≈ 0.82 (±0.02). If recall < 0.80, STOP — the OpenAlex step is spuriously matching fabricated fakes; tighten `match_any` for the OpenAlex candidate or drop the step. Do not ship a recall regression.

- [ ] **Step 2: Live subset + easy set**

Run: `cd eval && python modec_c1_run.py` and `cd eval && python eval_c1.py datasets/c1_references.jsonl`
Record BitNet/KAN/LoRA unresolved ratios (expect BitNet 0.50 / LoRA 0.55 to drop) and easy FP/recall.

- [ ] **Step 3: Record honestly**

Add `c1_second_resolver` block to `eval/results-2026-06.json` with: hard recall+FP after, easy recall+FP after, subset before {BitNet:0.50, KAN:0.10, LoRA:0.55} → after {actual}, `run_date":"2026-06-05"`, and a `note`. Add a "### C1 second resolver (OpenAlex)" before→after section to `docs/calibration-2026-06.md`. Use ACTUAL numbers; if the subset did NOT improve, or recall moved, say so plainly.

- [ ] **Step 4: Sync verify.py to live**

```bash
cp /d/paper/hype_experiment_3/repo/skill/paper-verify/verify.py \
   "/c/Users/GMfatcat/.claude/skills/dissecting-paper-hype/paper-verify/verify.py"
```
Verify: `cd "/c/Users/GMfatcat/.claude/skills/dissecting-paper-hype/paper-verify" && python -c "import verify; print(hasattr(verify,'_search_reference_openalex'))"` → `True`.

- [ ] **Step 5: Commit**

```bash
cd /d/paper/hype_experiment_3/repo
git add eval/results-2026-06.json docs/calibration-2026-06.md eval/modec_c1_results_2026-06.json
git commit -m "eval(c1): measure second-resolver before->after (recall gate held); sync live

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Notes for the executor

- **Recall gate is the hard rule:** the whole point of round ② was learning that more match chances can crash recall. If hard recall drops below ~0.80, the second resolver must be tightened or removed — record the finding honestly either way.
- `resolve_refs` return shape stays `{provided_checked, provided_unresolved}`.
- OpenAlex step fires only on Crossref miss (bounded extra calls).
- Push is gated — local only until the user says "push".
