# GROBID-backed reference extraction — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional GROBID reference-extraction path to `pdf-extract`: when a GROBID service is reachable, use it for high-quality references; otherwise fall back to the existing regex. Emit a `references_source` field. Full-text path and `paper-verify` unchanged.

**Architecture:** Augment existing `skill/pdf-extract/extract.py`. New: `parse_grobid_tei` (pure, stdlib XML), `_grobid_post` (network seam, monkeypatchable), `grobid_references` (returns refs or `None`), `_refs_via_grobid_or_regex` (decision), and `references_source` threaded through `_result`. GROBID is opt-in via env `GROBID_URL`; unreachable → regex fallback (behaviour identical to today). Pure + decision logic are unit-tested with no network/GROBID (inline TEI fixture + injected fake `grobid_fn`); live GROBID only for end-to-end smokes.

**Tech Stack:** Python 3.11 stdlib (`urllib`, `xml.etree.ElementTree`, `os`); pytest; GROBID lite/CRF Docker (separate service).

**Spec:** `docs/design/2026-06-04-grobid-references-design.md`

**IMPORTANT — existing file:** `skill/pdf-extract/extract.py` already exists (detect_source, strip_html, parse_arxiv_html, split_references, assess_text_layer, http_get, fetch_text, extract_pdf_text, _result, _fail, _extract_pdf, extract, format_output, CLI). This plan **augments** it. Read it first.

**Hard gate vs best-effort:** Tasks 1–4 (unit + decision tests) must pass with **no GROBID running** — they prove both the GROBID-active logic (via fakes) and the fallback. Task 5 (live-GROBID smokes) is best-effort: if a GROBID container can't be started in the environment, record the smokes as deferred and proceed — do NOT block completion on it.

---

## File Structure
| File | Change |
|---|---|
| `repo/skill/pdf-extract/extract.py` | add GROBID functions + decision order + `references_source` |
| `repo/skill/pdf-extract/test_extract.py` | add unit + decision tests; mark integration |
| `repo/skill/pdf-extract/README.md` | how to run GROBID lite/CRF, `GROBID_URL`, `references_source`, opt-in |
| `repo/skill/SKILL.md` | Mode C 取文 note: refs prefer GROBID if running |

---

## Task 1: `parse_grobid_tei` — pure TEI → reference strings

**Files:** Modify `extract.py`, `test_extract.py`

- [ ] **Step 1: Add the failing test**
```python
GROBID_TEI_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
<text><back><listBibl>
<biblStruct><analytic>
  <title level="a">Attention Is All You Need</title>
  <author><persName><surname>Vaswani</surname></persName></author>
  <author><persName><surname>Shazeer</surname></persName></author>
</analytic><monogr><imprint><date when="2017">2017</date></imprint></monogr></biblStruct>
<biblStruct><analytic>
  <title level="a">Deep Residual Learning for Image Recognition</title>
  <author><persName><surname>He</surname></persName></author>
</analytic><monogr><imprint><date when="2016"/></imprint></monogr></biblStruct>
<biblStruct><note type="raw_reference">Some Author. An untitled raw reference string only. 2020.</note></biblStruct>
</listBibl></back></text></TEI>"""

def test_parse_grobid_tei_structured_and_raw():
    refs = extract.parse_grobid_tei(GROBID_TEI_FIXTURE)
    assert len(refs) == 3
    assert "Attention Is All You Need" in refs[0]
    assert "Vaswani" in refs[0] and "2017" in refs[0]
    assert "Deep Residual Learning" in refs[1]
    assert "raw reference string" in refs[2]  # raw_reference fallback used

def test_parse_grobid_tei_bad_xml_returns_empty():
    assert extract.parse_grobid_tei("not xml <<<") == []
```

- [ ] **Step 2: Run, verify FAIL** — `cd repo/skill/pdf-extract && python -m pytest test_extract.py -k grobid_tei -v`

- [ ] **Step 3: Implement** — add near the top of extract.py with the other imports: `import os` and `import xml.etree.ElementTree as ET`; add constant `_TEI = "{http://www.tei-c.org/ns/1.0}"`. Then add:
```python
def parse_grobid_tei(xml):
    refs = []
    try:
        root = ET.fromstring(xml)
    except Exception:
        return refs
    for bib in root.iter(f"{_TEI}biblStruct"):
        titles = [t.text.strip() for t in bib.iter(f"{_TEI}title") if t.text and t.text.strip()]
        surnames = [s.text.strip() for s in bib.iter(f"{_TEI}surname") if s.text and s.text.strip()]
        years = []
        for d in bib.iter(f"{_TEI}date"):
            y = d.get("when") or (d.text or "")
            if y:
                years.append(y[:4])
        parts = []
        if surnames:
            parts.append(", ".join(surnames))
        if titles:
            parts.append(titles[0])
        if years:
            parts.append(years[0])
        s = ". ".join(parts).strip()
        if not s:
            note = bib.find(f".//{_TEI}note[@type='raw_reference']")
            if note is not None and note.text:
                s = note.text.strip()
        if s and len(s) > 5:
            refs.append(s)
    return refs
```

- [ ] **Step 4: Run, verify PASS** — `python -m pytest test_extract.py -k grobid_tei -v`

- [ ] **Step 5: Commit**
```bash
cd /d/paper/hype_experiment_3/repo
git add skill/pdf-extract/extract.py skill/pdf-extract/test_extract.py
git commit -m "feat(pdf-extract): parse_grobid_tei (pure TEI -> reference strings)"
```

---

## Task 2: `grobid_references` + `_grobid_post` (network seam)

**Files:** Modify `extract.py`, `test_extract.py`

- [ ] **Step 1: Add the failing test** (monkeypatch the network seam — no real GROBID)
```python
def test_grobid_references_parses_when_post_succeeds(monkeypatch):
    monkeypatch.setattr(extract, "_grobid_post", lambda url, pdf, timeout=60: GROBID_TEI_FIXTURE)
    refs = extract.grobid_references(b"%PDF-bytes", "http://localhost:8070")
    assert len(refs) == 3 and "Attention Is All You Need" in refs[0]

def test_grobid_references_none_on_post_error(monkeypatch):
    def boom(url, pdf, timeout=60): raise RuntimeError("connection refused")
    monkeypatch.setattr(extract, "_grobid_post", boom)
    assert extract.grobid_references(b"x", "http://localhost:8070") is None

def test_grobid_references_none_when_no_url():
    assert extract.grobid_references(b"x", None) is None
    assert extract.grobid_references(b"x", "") is None
```

- [ ] **Step 2: Run, verify FAIL**

- [ ] **Step 3: Implement** — append to extract.py:
```python
def _grobid_post(url, pdf_bytes, timeout=60):
    boundary = "----pdfextractGROBIDboundary"
    body = (
        ("--" + boundary + "\r\n").encode()
        + b'Content-Disposition: form-data; name="input"; filename="paper.pdf"\r\n'
        + b"Content-Type: application/pdf\r\n\r\n"
        + pdf_bytes + b"\r\n"
        + ("--" + boundary + "--\r\n").encode()
    )
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                 "Accept": "application/xml"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def grobid_references(pdf_bytes, grobid_url, timeout=60):
    if not grobid_url:
        return None
    endpoint = grobid_url.rstrip("/") + "/api/processReferences"
    try:
        xml = _grobid_post(endpoint, pdf_bytes, timeout)
    except Exception:
        return None
    return parse_grobid_tei(xml)
```

- [ ] **Step 4: Run, verify PASS**

- [ ] **Step 5: Commit**
```bash
git add skill/pdf-extract/extract.py skill/pdf-extract/test_extract.py
git commit -m "feat(pdf-extract): grobid_references via /api/processReferences (None on failure)"
```

---

## Task 3: decision order + `references_source` (the wiring)

**Files:** Modify `extract.py`, `test_extract.py`

- [ ] **Step 1: Add failing tests** (decision logic via injected fake `grobid_fn`, no network)
```python
def test_extract_pdf_uses_grobid_when_available():
    r = extract.extract(
        "https://x.org/p.pdf",
        bytes_fetcher=lambda u: b"%PDF",
        pdf_text=lambda b: "Body text. References [1] regex ref one here 2019.",
        grobid_fn=lambda pdf, url: ["GROBID Ref A 2017", "GROBID Ref B 2018", "GROBID Ref C 2019"],
        grobid_url="http://localhost:8070")
    assert r["references_source"] == "grobid"
    assert r["references_count"] == 3 and "GROBID Ref A" in r["references"][0]

def test_extract_pdf_regex_fallback_when_grobid_none():
    r = extract.extract(
        "https://x.org/p.pdf",
        bytes_fetcher=lambda u: b"%PDF",
        pdf_text=lambda b: "Body. References [1] First real cited paper title here 2019. [2] Second cited paper title here 2020.",
        grobid_fn=lambda pdf, url: None,
        grobid_url="http://localhost:8070")
    assert r["references_source"] == "regex_fallback"
    assert r["references_count"] >= 1

def test_extract_pdf_regex_when_grobid_disabled():
    r = extract.extract(
        "https://x.org/p.pdf",
        bytes_fetcher=lambda u: b"%PDF",
        pdf_text=lambda b: "Body. References [1] A cited paper title here 2019. [2] B cited paper title here 2020.",
        grobid_url=None)  # GROBID off
    assert r["references_source"] == "regex_fallback"

def test_extract_arxiv_html_with_refs_is_arxiv_source():
    r = extract.extract("2312.00752", html_fetcher=lambda u: ARXIV_HTML_FIXTURE,
                        grobid_url="http://localhost:8070",
                        grobid_fn=lambda pdf, url: ["should not be used"])
    assert r["references_source"] == "arxiv_html"
    assert r["references_count"] == 2  # from ARXIV_HTML_FIXTURE (Task-2 fixture in this file)

def test_extract_arxiv_html_no_refs_rescued_by_grobid():
    html_no_refs = "<html><body><section><p>ltx_ body selective state space</p></section></body></html>"
    r = extract.extract("2312.00752",
                        html_fetcher=lambda u: html_no_refs,
                        bytes_fetcher=lambda u: b"%PDF",
                        grobid_fn=lambda pdf, url: ["Rescued Ref 2023"],
                        grobid_url="http://localhost:8070")
    assert r["references_source"] == "grobid"
    assert "Rescued Ref" in r["references"][0]
```
(Note: `ARXIV_HTML_FIXTURE` already exists in test_extract.py from the original Task 2; it has 2 `ltx_bibitem`. Reuse it.)

- [ ] **Step 2: Run, verify FAIL**

- [ ] **Step 3: Implement** — make these edits in extract.py:

(a) Add `references_source` to `_result` — change its signature and dict:
```python
def _result(query, ok, source, coverage, text_layer, fulltext, refs, notes, references_source="none"):
    return {
        "query": query, "ok": ok, "source": source, "coverage": coverage,
        "text_layer": text_layer, "fulltext": fulltext, "fulltext_chars": len(fulltext or ""),
        "references": refs, "references_count": len(refs), "references_source": references_source,
        "notes": notes,
    }
```
(`_fail` calls `_result(... [], [msg])` — it will now get `references_source="none"` by default; leave `_fail` as is.)

(b) Add the decision helper:
```python
def _refs_via_grobid_or_regex(pdf_bytes, text_for_regex, grobid_fn, grobid_url):
    if grobid_url and pdf_bytes is not None:
        g = grobid_fn(pdf_bytes, grobid_url)
        if g:
            return g, "grobid"
    if text_for_regex:
        return split_references(text_for_regex), "regex_fallback"
    return [], "none"
```

(c) Rewrite `_extract_pdf` to take grobid params and use the helper:
```python
def _extract_pdf(query, url, bytes_fetcher, pdf_text, grobid_fn, grobid_url):
    try:
        data = bytes_fetcher(url)
    except Exception as e:
        return _fail(query, f"could not fetch PDF: {e}")
    try:
        text = pdf_text(data)
    except Exception as e:
        return _fail(query, f"PDF parse failed: {e}")
    has_layer, coverage = assess_text_layer(text)
    if not has_layer:
        return _result(query, True, "pdf_textlayer", "none", False, "", [],
                       ["no text layer (image/scanned PDF); no OCR — fall back"],
                       references_source="none")
    refs, rsrc = _refs_via_grobid_or_regex(data, text, grobid_fn, grobid_url)
    return _result(query, True, "pdf_textlayer", coverage, True, text, refs,
                   ["PDF text layer extracted; refs via " + rsrc], references_source=rsrc)
```

(d) Rewrite `extract` to thread grobid params + arXiv-HTML-0-refs rescue:
```python
def extract(identifier, html_fetcher=fetch_text, bytes_fetcher=http_get,
            pdf_text=extract_pdf_text, grobid_fn=grobid_references, grobid_url=None):
    stype, val = detect_source(identifier)
    if stype == "arxiv":
        try:
            html = html_fetcher(ARXIV_HTML.format(id=val))
        except Exception:
            html = None
        if html and "ltx_" in html:
            fulltext, refs = parse_arxiv_html(html)
            if refs:
                return _result(identifier, True, "arxiv_html", "full", True, fulltext, refs,
                               ["arXiv HTML used"], references_source="arxiv_html")
            pdf_bytes = None
            if grobid_url:
                try:
                    pdf_bytes = bytes_fetcher(ARXIV_PDF.format(id=val))
                except Exception:
                    pdf_bytes = None
            g_refs, rsrc = _refs_via_grobid_or_regex(pdf_bytes, fulltext, grobid_fn, grobid_url)
            return _result(identifier, True, "arxiv_html", "full", True, fulltext, g_refs,
                           ["arXiv HTML used; refs via " + rsrc], references_source=rsrc)
        return _extract_pdf(identifier, ARXIV_PDF.format(id=val), bytes_fetcher, pdf_text, grobid_fn, grobid_url)
    if stype == "pdf_url":
        return _extract_pdf(identifier, val, bytes_fetcher, pdf_text, grobid_fn, grobid_url)
    return _fail(identifier, "unknown identifier; expected arXiv id or PDF URL")
```

- [ ] **Step 4: Run, verify PASS** — `python -m pytest test_extract.py -v` (all unit tests, old + new, pass with NO GROBID running).

- [ ] **Step 5: Commit**
```bash
git add skill/pdf-extract/extract.py skill/pdf-extract/test_extract.py
git commit -m "feat(pdf-extract): GROBID-first refs decision order + references_source"
```

---

## Task 4: CLI wiring (env `GROBID_URL`)

**Files:** Modify `extract.py`, `test_extract.py`

- [ ] **Step 1: Add failing test**
```python
def test_format_output_includes_references_source():
    r = extract._result("q", True, "arxiv_html", "full", True, "text", ["a"], ["n"],
                        references_source="grobid")
    import json as _j
    assert _j.loads(extract.format_output(r))["references_source"] == "grobid"
```

- [ ] **Step 2: Run, verify FAIL** (references_source not yet in a passing format path — it will pass once Task 3 done; if already green, still add the explicit test). Actually run it; if it passes due to Task 3, proceed — this test locks the contract.

- [ ] **Step 3: Implement** — update the `__main__` block to read `GROBID_URL` from env and pass it:
```python
if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "notes": ["usage: python extract.py <arXiv id | PDF URL>"]}))
        sys.exit(0)
    grobid_url = os.environ.get("GROBID_URL", "http://localhost:8070")
    print(format_output(extract(sys.argv[1], grobid_url=grobid_url)))
```
(Default `http://localhost:8070`: if no GROBID is running, the POST fails fast with connection-refused → `grobid_references` returns None → regex fallback. No hang.)

- [ ] **Step 4: Run, verify PASS** — `python -m pytest test_extract.py -v` all green.

- [ ] **Step 5: Commit**
```bash
git add skill/pdf-extract/extract.py skill/pdf-extract/test_extract.py
git commit -m "feat(pdf-extract): wire GROBID_URL env into CLI"
```

---

## Task 5: Live-GROBID integration smokes (best-effort)

**Files:** Modify `test_extract.py` (add `@pytest.mark.integration` tests)

- [ ] **Step 1: Add integration tests**
```python
@pytest.mark.integration
def test_integration_grobid_llama_refs():
    # Requires a running GROBID at $GROBID_URL (default localhost:8070)
    import os
    r = extract.extract("2302.13971", grobid_url=os.environ.get("GROBID_URL", "http://localhost:8070"))
    assert r["ok"]
    assert r["references_source"] == "grobid"
    assert r["references_count"] >= 15  # GROBID should get far more than regex's ~2

@pytest.mark.integration
def test_integration_grobid_down_falls_back():
    # Point at a dead port -> must fall back to regex, not crash
    r = extract.extract("2302.13971", grobid_url="http://localhost:9")
    assert r["ok"]
    assert r["references_source"] in ("regex_fallback", "none")
```

- [ ] **Step 2: Try to start GROBID lite/CRF and run smokes**
```bash
docker run -d --rm --name grobid -p 8070:8070 lfoppiano/grobid:0.8.0
# wait for startup, then check:
curl -s http://localhost:8070/api/isalive   # expect: true
cd /d/paper/hype_experiment_3/repo/skill/pdf-extract
python -m pytest -m integration -v
```
Expected: `test_integration_grobid_llama_refs` PASS with `references_count >= 15`; `test_integration_grobid_down_falls_back` PASS.
**If GROBID cannot be pulled/started in this environment** (multi-GB image, RAM, or time): record that the live smokes are **deferred** (note it in the commit message), confirm the `grobid_down_falls_back` test still passes (it points at a dead port, needs no GROBID), and proceed. Unit + decision tests (Tasks 1–4) are the completion gate. If you started GROBID, stop it after: `docker stop grobid`.

- [ ] **Step 3: Commit**
```bash
cd /d/paper/hype_experiment_3/repo
git add skill/pdf-extract/test_extract.py
git commit -m "test(pdf-extract): GROBID integration smokes (best-effort)"
```

---

## Task 6: README + SKILL.md note

**Files:** Modify `repo/skill/pdf-extract/README.md`, `repo/skill/SKILL.md`

- [ ] **Step 1: README — add a GROBID section**
Append to `repo/skill/pdf-extract/README.md`:
```markdown
## Better references via GROBID (optional)
By default references come from arXiv HTML (when present) or a regex heuristic (best-effort). For high-quality references (F1~0.9), run a GROBID service and point `pdf-extract` at it:

    # start a lightweight CRF GROBID (image is ~0.3–1 GB; check GROBID docs for the current tag)
    docker run -d --rm --name grobid -p 8070:8070 lfoppiano/grobid:0.8.0
    curl -s http://localhost:8070/api/isalive   # -> true

    export GROBID_URL=http://localhost:8070      # default is already http://localhost:8070
    python extract.py "2302.13971"               # references now via GROBID

- `GROBID_URL` unset/unreachable → identical to today (regex fallback); GROBID is **opt-in**.
- Output field **`references_source`**: `arxiv_html` | `grobid` | `regex_fallback` | `none` — tells you (and Mode C) how refs were obtained; confidence: grobid > arxiv_html > regex_fallback.
- The full deep-learning image `grobid/grobid:0.8.2` gives marginally better F1 but is ~10 GB / needs more RAM; the CRF image is recommended here.
```

- [ ] **Step 2: SKILL.md — Mode C 取文 note** — find the existing line:
`- **全文與引用**:跑 \`pdf-extract "<arXiv id/PDF URL>"\`(skill/pdf-extract/)→ \`fulltext\` 餵 C2/C3 文字掃描;\`references\` 餵 \`paper-verify <id> --refs -\` 做 C1。\`coverage:none\`(圖片化 PDF)→ C2/C3 標受限,同今。`
(it may have a slightly longer tail; match on the leading portion up to a unique substring). Append after it:
`  - **引用品質**:pdf-extract 的 \`references_source\` 顯示引用怎麼來(\`grobid\` > \`arxiv_html\` > \`regex_fallback\`)。若有跑 GROBID 服務(\`GROBID_URL\`),引用會大幅更完整 → C1 更可信;沒跑就是 best-effort regex,C1 信心降一級。`

- [ ] **Step 3: Verify + commit**
```bash
cd /d/paper/hype_experiment_3/repo
grep -n "GROBID\|references_source" skill/pdf-extract/README.md skill/SKILL.md
git add skill/pdf-extract/README.md skill/SKILL.md
git commit -m "docs(pdf-extract): document optional GROBID + references_source"
```

---

## Task 7: Sync to live + final commit

**Files:** copy extract.py + README to live; apply the SKILL.md note to live

- [ ] **Step 1: Copy tool files to live**
```bash
cp /d/paper/hype_experiment_3/repo/skill/pdf-extract/extract.py /d/paper/hype_experiment_3/repo/skill/pdf-extract/README.md "/c/Users/GMfatcat/.claude/skills/dissecting-paper-hype/pdf-extract/"
```
(test_extract.py / pytest.ini stay in repo only.)

- [ ] **Step 2: Apply the SKILL.md Mode C note to the LIVE skill** (`C:\Users\GMfatcat\.claude\skills\dissecting-paper-hype\SKILL.md`) using the same anchor + appended bullet from Task 6 Step 2. Read first; do NOT whole-file copy.

- [ ] **Step 3: Verify live**
```bash
grep -n "references_source\|GROBID" "/c/Users/GMfatcat/.claude/skills/dissecting-paper-hype/pdf-extract/extract.py" "/c/Users/GMfatcat/.claude/skills/dissecting-paper-hype/SKILL.md" | head
```

- [ ] **Step 4: Final repo commit (local, NO push)**
```bash
cd /d/paper/hype_experiment_3/repo
git add -A
git commit -m "chore(grobid): sync GROBID refs path + docs to live" --allow-empty
git log --oneline -1 ; git status -sb | head -1
```

---

## Self-Review
- **Spec coverage:** §2 GROBID service/opt-in/`GROBID_URL`→T2/T4; §3 `parse_grobid_tei`→T1, `grobid_references`→T2, decision order→T3, full-text unchanged→T3 (extract() leaves fulltext path intact); §4 output `references_source`→T3/T4; §5 dependency tradeoff→T6 README; §6 testing (pure fixture, decision via fake, integration)→T1/T3/T5; §7 components (no paper-verify change)→all.
- **Placeholder scan:** none — all code given. GROBID image tag pinned to `lfoppiano/grobid:0.8.0` in README/smoke with a note to check current tag; code is image-agnostic so the tag is ops-only.
- **Consistency:** `parse_grobid_tei`, `_grobid_post`, `grobid_references`, `_refs_via_grobid_or_regex` signatures match across tasks; `references_source` values `arxiv_html|grobid|regex_fallback|none` identical in `_result` (T3), tests (T3/T4), README + SKILL note (T6). `extract(... grobid_fn=grobid_references, grobid_url=None)` injection points match the tests. `_extract_pdf` new signature used consistently in `extract`.
- **Fallback safety:** every GROBID failure path (no url / post raises / empty result / PDF fetch fails) routes to regex or `none` — proven by Tasks 2–3 unit tests with NO GROBID. Completion gate = Tasks 1–4; Task 5 best-effort.
