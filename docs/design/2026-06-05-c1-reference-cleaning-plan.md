# C1 Reference Cleaning — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Strip arXiv-HTML citation-key noise from extracted references at the `pdf-extract` source so C1 false-positives drop without hurting recall.

**Architecture:** One pure function `clean_reference` in `pdf-extract/extract.py`, applied at the single output chokepoint `_result(...)` so every source (arxiv_html/grobid/regex/pdf) is cleaned uniformly.

**Tech Stack:** Python 3 stdlib (`re`); pytest.

**Spec:** `docs/design/2026-06-05-c1-reference-cleaning-design.md`

**Conventions:** Work in `D:\paper\hype_experiment_3\repo`. Run pytest from `skill/pdf-extract/` (where its pytest.ini + test_extract.py live). Pure-function unit = hard TDD gate. Commit after each task; do NOT push. Commit trailer EXACTLY: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

## Task 1: `clean_reference` pure function

**Files:**
- Modify: `skill/pdf-extract/extract.py` (add `clean_reference` near `split_references`)
- Test: `skill/pdf-extract/test_extract.py`

- [ ] **Step 1: Write failing tests**

Add to `test_extract.py`:

```python
def test_clean_reference_strips_citation_key():
    assert extract.clean_reference("BZB + [19] Yonatan Bisk, Rowan Zellers").startswith("Yonatan Bisk")
    assert extract.clean_reference("Com [23] Together Computer. Redpajama") == "Together Computer. Redpajama"
    assert extract.clean_reference("FAHA [23] Elias Frantar").startswith("Elias Frantar")
    assert extract.clean_reference("MXBS [16] Stephen Merity").startswith("Stephen Merity")

def test_clean_reference_strips_bare_index():
    assert extract.clean_reference("[12] Ming-Jun Lai and Zhaiming Shen").startswith("Ming-Jun Lai")

def test_clean_reference_leaves_clean_unchanged():
    s = "Vaswani et al. Attention Is All You Need. 2017."
    assert extract.clean_reference(s) == s

def test_clean_reference_conservative_keeps_author_year():
    s = "Allen-Zhu & Li (2019) Zeyuan Allen-Zhu and Yuanzhi Li. What Can ResNet Learn"
    assert extract.clean_reference(s) == s

def test_clean_reference_empty():
    assert extract.clean_reference(None) == ""
    assert extract.clean_reference("") == ""

def test_clean_reference_idempotent():
    once = extract.clean_reference("HCB + [19] Yanping Huang, Youlong Cheng")
    assert extract.clean_reference(once) == once
```

- [ ] **Step 2: Run to verify fail**

Run: `cd skill/pdf-extract && python -m pytest test_extract.py -k clean_reference -v`
Expected: FAIL (`module 'extract' has no attribute 'clean_reference'`)

- [ ] **Step 3: Implement `clean_reference`**

Add to `extract.py` (near `split_references`, line ~51):

```python
_CITE_KEY = re.compile(r"^[A-Z][A-Za-z]{0,7}(?:\s*\+)?\s*\[\d{1,4}\]\s+")
_BARE_INDEX = re.compile(r"^\[\d{1,4}\]\s+")

def clean_reference(s):
    """Strip arXiv-HTML citation-key noise from the START of a reference string.

    Removes a leading author-initial key + bracketed index ("BZB + [19] ",
    "FAHA [23] ", "MXBS [16] ") or a bare leading index ("[12] "). Conservative:
    only the well-characterized leading patterns are stripped; author-year
    prefixes ("Allen-Zhu & Li (2019) ") and the rest are left intact. Idempotent.
    """
    if not s:
        return ""
    out = _CITE_KEY.sub("", s)
    if out == s:
        out = _BARE_INDEX.sub("", s)
    return out.strip()
```

- [ ] **Step 4: Run to verify pass**

Run: `cd skill/pdf-extract && python -m pytest test_extract.py -k clean_reference -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
cd /d/paper/hype_experiment_3/repo
git add skill/pdf-extract/extract.py skill/pdf-extract/test_extract.py
git commit -m "feat(pdf-extract): clean_reference strips citation-key noise (pure)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Apply cleaning at the `_result` chokepoint

**Files:**
- Modify: `skill/pdf-extract/extract.py` (`_result`)
- Test: `skill/pdf-extract/test_extract.py`

- [ ] **Step 1: Read `_result` first.** It currently looks like:

```python
def _result(query, ok, source, coverage, text_layer, fulltext, refs, notes, references_source="none"):
    return {
        ... "references": refs, "references_count": len(refs), "references_source": references_source, ...
    }
```

(Confirm exact body before editing; only the refs handling changes.)

- [ ] **Step 2: Write failing test**

Add to `test_extract.py`. The `"MXBS [16] "` entry is a citation key with an
empty body → cleans to `""` → must be dropped, proving `_result` both cleans and
filters empties. (Confirm the positional arg order against the real `_result`
signature you read in Step 1.)

```python
def test_result_cleans_and_drops_empty_refs():
    r = extract._result("q", True, "arxiv_html", "full", True, "body text",
                        ["BZB + [19] Yonatan Bisk, Rowan Zellers",
                         "MXBS [16] ",              # key only -> cleans to "" -> dropped
                         "Vaswani et al. Attention Is All You Need. 2017."],
                        ["note"], references_source="arxiv_html")
    assert r["references"][0].startswith("Yonatan Bisk")
    assert r["references"][-1].startswith("Vaswani")
    assert all(x for x in r["references"])          # no empty strings
    assert r["references_count"] == len(r["references"]) == 2
```

- [ ] **Step 3: Run to verify fail**

Run: `cd skill/pdf-extract && python -m pytest test_extract.py::test_result_cleans_and_drops_empty_refs -v`
Expected: FAIL (refs not cleaned; count is 3, `MXBS [16] ` present)

- [ ] **Step 4: Implement the cleaning in `_result`**

In `_result`, before building the dict, insert:

```python
    refs = [c for c in (clean_reference(r) for r in (refs or [])) if c]
```

so `"references": refs, "references_count": len(refs)` now use the cleaned list.

- [ ] **Step 5: Run to verify pass**

Run: `cd skill/pdf-extract && python -m pytest test_extract.py::test_result_cleans_and_drops_empty_refs -v`
Expected: PASS

- [ ] **Step 6: Full suite — no regression**

Run: `cd skill/pdf-extract && python -m pytest -m "not integration" -q`
Expected: all existing + new unit tests pass. (If `test_extract.py` has integration-marked tests that need network, run the non-integration set here.)

- [ ] **Step 7: Commit**

```bash
cd /d/paper/hype_experiment_3/repo
git add skill/pdf-extract/extract.py skill/pdf-extract/test_extract.py
git commit -m "feat(pdf-extract): clean references at _result chokepoint (drop key-only)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Re-measure C1, record honestly, sync live

**Files:**
- Run: `eval/modec_c1_run.py`, `eval/eval_c1.py`
- Modify: `eval/results-2026-06.json` (add `c1_cleaning` note), `docs/calibration-2026-06.md` (before→after line)
- Copy: `skill/pdf-extract/extract.py` → live

- [ ] **Step 1: Re-run the live C1 end-to-end on the subset**

Run: `cd eval && python modec_c1_run.py`
Record the printed unresolved ratios for BitNet / KAN / LoRA. Compare to the prior run (BitNet 0.50, KAN 0.125, LoRA 0.55 — from `docs/mode-c-test-2026-06.md`). Expect BitNet to drop materially; KAN ~unchanged; LoRA may improve only a little (author-year prefixes not stripped — honest).

- [ ] **Step 2: Confirm calibration recall not hurt**

Run: `cd eval && python eval_c1.py datasets/c1_references_hard.jsonl`
Expected: recall ≈ 0.82, FP ≈ unchanged (the calibration refs carry no citation-key prefix, so cleaning is a no-op there). If recall dropped, STOP and investigate — cleaning must not harm recall.

- [ ] **Step 3: Record results honestly**

Add to `eval/results-2026-06.json` a `c1_cleaning` block: `{"run_date": "2026-06-05", "subset_before": {"BitNet": 0.50, "KAN": 0.125, "LoRA": 0.55}, "subset_after": {<actual>}, "hard_recall_after": <actual>, "note": "<one line>"}`. Use ACTUAL measured numbers. Add a short "### C1 reference cleaning (before → after)" note to `docs/calibration-2026-06.md` narrating the subset improvement and that recall held. If BitNet did NOT drop, say so plainly.

- [ ] **Step 4: Sync extract.py to live**

```bash
cp /d/paper/hype_experiment_3/repo/skill/pdf-extract/extract.py \
   "/c/Users/GMfatcat/.claude/skills/dissecting-paper-hype/pdf-extract/extract.py"
```
Verify: `cd "/c/Users/GMfatcat/.claude/skills/dissecting-paper-hype/pdf-extract" && python -c "import extract; print(extract.clean_reference('FAHA [23] Elias Frantar'))"`
Expected: prints `Elias Frantar`.

- [ ] **Step 5: Commit**

```bash
cd /d/paper/hype_experiment_3/repo
git add eval/results-2026-06.json docs/calibration-2026-06.md
git commit -m "eval(c1): measure reference-cleaning before->after; sync extract.py live

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Notes for the executor

- **Honesty gate:** record the actual before→after numbers, including if the drop is smaller than hoped. The conservative cleaner only targets the documented citation-key pattern; LoRA-style author-year prefixes remain (that's expected, left for round ③). `refs_unresolved` stays advisory.
- Do not touch `paper-verify` matching logic.
- Push is gated — everything stays local until the user says "push".
