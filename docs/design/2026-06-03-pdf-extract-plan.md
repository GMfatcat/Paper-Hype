# pdf-extract (full-text + refs) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Dockerized `pdf-extract` CLI (arXiv HTML first, text-layer PDF via PyMuPDF, no OCR) that returns a paper's full text + reference list, AND add `--refs` batch-resolution to the existing `paper-verify` so Mode C's C1/C2/C3 work on real text.

**Architecture:** Pure functions (`detect_source`, `strip_html`, `parse_arxiv_html`, `split_references`, `assess_text_layer`, and in paper-verify `match_reference`/`resolve_refs`) hold all logic and unit-test with inline fixtures and NO third-party imports. `fitz` (PyMuPDF) is imported lazily only inside `extract_pdf_text`; network only in `http_get`/`fetch_text`. Orchestration is dependency-injected so it tests without network or fitz. Integration smokes exercise real arXiv/PDF + Docker.

**Tech Stack:** Python 3.11; `PyMuPDF` (pip, no system libs) for PDF text; stdlib `urllib`/`re`/`html` for fetch + arXiv-HTML parse; pytest (dev); Docker (`python:3.11-slim`).

**Spec:** `docs/design/2026-06-03-pdf-extract-design.md`

**Where to build:** repo at `repo/skill/pdf-extract/` (new) + edits to `repo/skill/paper-verify/verify.py`. Live skill mirror at `C:\Users\GMfatcat\.claude\skills\dissecting-paper-hype\`; Task 9 syncs. Commits local (no push) unless told.

**Local deps for tests:** unit tests need only pytest (no fitz). For integration smokes try `python -m pip install pymupdf`; if that fails locally, run integration through the Docker image built in Task 6. Never weaken assertions — if a dep/network is unavailable, report it.

---

## File Structure
| File | Responsibility |
|---|---|
| `repo/skill/pdf-extract/extract.py` | tool: pure parse/split logic + lazy-fitz PDF path + fetch + CLI |
| `repo/skill/pdf-extract/test_extract.py` | pytest: unit (inline fixtures) + integration smokes |
| `repo/skill/pdf-extract/Dockerfile` | container (`python:3.11-slim` + `pip install pymupdf`) |
| `repo/skill/pdf-extract/README.md` | usage, JSON shape, limits |
| `repo/skill/pdf-extract/pytest.ini` | `integration` marker |
| `repo/skill/paper-verify/verify.py` | ADD `match_reference`, `resolve_refs`, `--refs` CLI |
| `repo/skill/paper-verify/test_verify.py` | ADD tests for ref matching/resolution |
| `repo/skill/SKILL.md` | Mode C 取文: add pdf-extract + C1-via-`--refs` |
| `repo/skill/references/templates.md` | Template F C1: use `paper-verify --refs` when refs available |

Constants in extract.py: `ARXIV_HTML = "https://arxiv.org/html/{id}"`, `ARXIV_PDF = "https://arxiv.org/pdf/{id}"`, `TEXT_LAYER_MIN = 200`.

---

## Task 1: `detect_source()` — identifier → (type, value)

**Files:** Create `repo/skill/pdf-extract/extract.py`, `repo/skill/pdf-extract/test_extract.py`

- [ ] **Step 1: Failing test**
```python
# test_extract.py
import extract

def test_detect_arxiv_bare():
    assert extract.detect_source("2312.00752") == ("arxiv", "2312.00752")
    assert extract.detect_source("arXiv:2606.02437") == ("arxiv", "2606.02437")
    assert extract.detect_source("2312.00752v3") == ("arxiv", "2312.00752")

def test_detect_arxiv_url():
    assert extract.detect_source("https://arxiv.org/abs/2312.00752") == ("arxiv", "2312.00752")
    assert extract.detect_source("https://arxiv.org/pdf/2312.00752") == ("arxiv", "2312.00752")

def test_detect_pdf_url():
    assert extract.detect_source("https://example.org/paper.pdf") == ("pdf_url", "https://example.org/paper.pdf")

def test_detect_unknown():
    assert extract.detect_source("just a title")[0] == "unknown"
```

- [ ] **Step 2: Run, verify FAIL** — `cd repo/skill/pdf-extract && python -m pytest test_extract.py -v`

- [ ] **Step 3: Implement**
```python
# extract.py
import json
import re
import sys
import urllib.request
from html import unescape

ARXIV_HTML = "https://arxiv.org/html/{id}"
ARXIV_PDF = "https://arxiv.org/pdf/{id}"
TEXT_LAYER_MIN = 200

_ARXIV_BARE = re.compile(r'^(\d{4}\.\d{4,5})(v\d+)?$')
_ARXIV_URL = re.compile(r'arxiv\.org/(?:abs|pdf|html)/(\d{4}\.\d{4,5})')


def detect_source(identifier):
    ident = (identifier or "").strip()
    low = ident.lower()
    m = _ARXIV_URL.search(low)
    if m:
        return ("arxiv", m.group(1))
    bare = low.replace("arxiv:", "").strip()
    m2 = _ARXIV_BARE.match(bare)
    if m2:
        return ("arxiv", m2.group(1))
    if low.startswith("http"):
        return ("pdf_url", ident)
    return ("unknown", ident)
```

- [ ] **Step 4: Run, verify PASS**

- [ ] **Step 5: Commit**
```bash
cd repo/skill/pdf-extract && git add extract.py test_extract.py
git commit -m "feat(pdf-extract): detect_source"
```

---

## Task 2: `strip_html()` + `parse_arxiv_html()`

**Files:** Modify `extract.py`, `test_extract.py`

- [ ] **Step 1: Failing test** (fixture mimics arXiv ar5iv HTML structure)
```python
ARXIV_HTML_FIXTURE = """
<html><body>
<div class="ltx_abstract"><p>We introduce selective state space models.</p></div>
<section><h2>1 Introduction</h2><p>Mamba is a sequence model.</p>
<script>var x=1;</script></section>
<ul class="ltx_biblist">
  <li class="ltx_bibitem">A. Vaswani et al. Attention is all you need. NeurIPS 2017.</li>
  <li class="ltx_bibitem">A. Gu et al. Efficiently modeling long sequences. ICLR 2022.</li>
</ul>
</body></html>
"""

def test_strip_html_removes_tags_and_scripts():
    out = extract.strip_html("<p>Hello <b>world</b></p><script>bad()</script>")
    assert "Hello world" in out and "bad()" not in out

def test_parse_arxiv_html_body_and_refs():
    fulltext, refs = extract.parse_arxiv_html(ARXIV_HTML_FIXTURE)
    assert "selective state space" in fulltext
    assert "Mamba is a sequence model" in fulltext
    assert len(refs) == 2
    assert "Attention is all you need" in refs[0]
    # bibliography text should not pollute body refs duplication beyond the list
```

- [ ] **Step 2: Run, verify FAIL**

- [ ] **Step 3: Implement (append to extract.py)**
```python
def strip_html(html):
    html = re.sub(r'(?is)<(script|style)\b.*?</\1>', ' ', html)
    text = re.sub(r'(?s)<[^>]+>', ' ', html)
    text = unescape(text)
    return re.sub(r'\s+', ' ', text).strip()


def parse_arxiv_html(html):
    refs = []
    for m in re.finditer(r'(?is)<li[^>]*ltx_bibitem[^>]*>(.*?)</li>', html):
        t = strip_html(m.group(1))
        if t:
            refs.append(t)
    body_html = re.sub(r'(?is)<(ul|ol)[^>]*ltx_biblist.*?</\1>', ' ', html)
    return strip_html(body_html), refs
```

- [ ] **Step 4: Run, verify PASS**

- [ ] **Step 5: Commit**
```bash
git add extract.py test_extract.py
git commit -m "feat(pdf-extract): strip_html + parse_arxiv_html"
```

---

## Task 3: `split_references()` + `assess_text_layer()`

**Files:** Modify `extract.py`, `test_extract.py`

- [ ] **Step 1: Failing test**
```python
def test_split_references_bracketed():
    block = ("Some body text here. References [1] A. Vaswani. Attention is all you need. 2017. "
             "[2] A. Gu. Mamba long sequences modeling paper. 2023.")
    refs = extract.split_references(block)
    assert len(refs) == 2
    assert "Vaswani" in refs[0] and "Gu" in refs[1]

def test_split_references_no_section_returns_few():
    # No 'References' heading -> best effort, should not crash
    assert isinstance(extract.split_references("no refs here"), list)

def test_assess_text_layer():
    assert extract.assess_text_layer("x" * 250) == (True, "full")
    assert extract.assess_text_layer("short") == (True, "partial")
    assert extract.assess_text_layer("") == (False, "none")
```

- [ ] **Step 2: Run, verify FAIL**

- [ ] **Step 3: Implement (append to extract.py)**
```python
def split_references(text):
    m = re.search(r'(?is)\b(references|bibliography)\b', text or "")
    tail = text[m.end():] if m else (text or "")
    parts = re.split(r'(?m)\s*\[\d+\]\s*', tail)
    entries = [re.sub(r'\s+', ' ', p).strip() for p in parts]
    return [e for e in entries if len(e) > 20]


def assess_text_layer(text, threshold=TEXT_LAYER_MIN):
    n = len((text or "").strip())
    if n >= threshold:
        return True, "full"
    if n > 0:
        return True, "partial"
    return False, "none"
```

- [ ] **Step 4: Run, verify PASS**

- [ ] **Step 5: Commit**
```bash
git add extract.py test_extract.py
git commit -m "feat(pdf-extract): split_references + assess_text_layer"
```

---

## Task 4: fetch helpers + `extract()` orchestration (dependency-injected)

**Files:** Modify `extract.py`, `test_extract.py`

- [ ] **Step 1: Failing test** (no network — inject fetchers)
```python
def test_extract_arxiv_html_path():
    r = extract.extract("2312.00752", html_fetcher=lambda url: ARXIV_HTML_FIXTURE)
    assert r["ok"] is True
    assert r["source"] == "arxiv_html"
    assert r["coverage"] == "full"
    assert r["references_count"] == 2
    assert "selective state space" in r["fulltext"]

def test_extract_pdf_path():
    r = extract.extract(
        "https://x.org/p.pdf",
        bytes_fetcher=lambda url: b"%PDF-fake",
        pdf_text=lambda b: "Body. References [1] Real Cited Paper title here 2020.")
    assert r["source"] == "pdf_textlayer"
    assert r["text_layer"] is True
    assert r["references_count"] == 1

def test_extract_image_pdf_no_text_layer():
    r = extract.extract("https://x.org/scan.pdf",
                        bytes_fetcher=lambda url: b"%PDF", pdf_text=lambda b: "")
    assert r["ok"] is True
    assert r["coverage"] == "none"
    assert r["text_layer"] is False

def test_extract_fetch_failure():
    def boom(url): raise RuntimeError("timeout")
    r = extract.extract("https://x.org/p.pdf", bytes_fetcher=boom)
    assert r["ok"] is False
```

- [ ] **Step 2: Run, verify FAIL**

- [ ] **Step 3: Implement (append to extract.py)**
```python
def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "pdf-extract/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_text(url, timeout=30):
    return http_get(url, timeout).decode("utf-8", "replace")


def extract_pdf_text(pdf_bytes):
    import fitz  # lazy — only needed on the PDF path
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def _result(query, ok, source, coverage, text_layer, fulltext, refs, notes):
    return {
        "query": query, "ok": ok, "source": source, "coverage": coverage,
        "text_layer": text_layer, "fulltext": fulltext, "fulltext_chars": len(fulltext or ""),
        "references": refs, "references_count": len(refs), "notes": notes,
    }


def _fail(query, msg):
    return _result(query, False, "none", "none", False, "", [], [msg])


def _extract_pdf(query, url, bytes_fetcher, pdf_text):
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
                       ["no text layer (image/scanned PDF); no OCR — fall back"])
    return _result(query, True, "pdf_textlayer", coverage, True, text,
                   split_references(text), ["PDF text layer extracted"])


def extract(identifier, html_fetcher=fetch_text, bytes_fetcher=http_get, pdf_text=extract_pdf_text):
    stype, val = detect_source(identifier)
    if stype == "arxiv":
        try:
            html = html_fetcher(ARXIV_HTML.format(id=val))
        except Exception:
            html = None
        if html and "ltx_" in html:
            fulltext, refs = parse_arxiv_html(html)
            return _result(identifier, True, "arxiv_html", "full", True, fulltext, refs, ["arXiv HTML used"])
        return _extract_pdf(identifier, ARXIV_PDF.format(id=val), bytes_fetcher, pdf_text)
    if stype == "pdf_url":
        return _extract_pdf(identifier, val, bytes_fetcher, pdf_text)
    return _fail(identifier, "unknown identifier; expected arXiv id or PDF URL")
```

- [ ] **Step 4: Run, verify PASS**

- [ ] **Step 5: Commit**
```bash
git add extract.py test_extract.py
git commit -m "feat(pdf-extract): fetch + extract orchestration (injectable)"
```

---

## Task 5: CLI + integration smokes (real arXiv/PDF, needs fitz)

**Files:** Modify `extract.py`, `test_extract.py`, Create `repo/skill/pdf-extract/pytest.ini`

- [ ] **Step 1: Failing unit test for CLI formatter**
```python
import json as _json, pytest

def test_format_output_valid_json():
    r = extract._result("q", True, "arxiv_html", "full", True, "text", ["a"], ["n"])
    parsed = _json.loads(extract.format_output(r))
    assert parsed["references_count"] == 1

@pytest.mark.integration
def test_integration_arxiv_html_mamba():
    r = extract.extract("2312.00752")
    assert r["ok"] and r["source"] == "arxiv_html"
    assert "state space" in r["fulltext"].lower()
    assert r["references_count"] > 0

@pytest.mark.integration
def test_integration_image_pdf_coverage_none():
    # A known image-only/scanned PDF URL (replace with a real one at run time if needed).
    r = extract.extract("https://arxiv.org/pdf/2606.02437")  # Mind Lab — image-encoded PDF
    assert r["ok"] is True
    assert r["coverage"] in ("none", "partial", "full")  # must not crash; ideally none
```

- [ ] **Step 2: Run unit, verify FAIL** (no format_output)

- [ ] **Step 3: Implement (append to extract.py)**
```python
def format_output(result):
    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "notes": ["usage: python extract.py <arXiv id | PDF URL>"]}))
        sys.exit(0)
    print(format_output(extract(sys.argv[1])))
```
Create `pytest.ini`:
```ini
[pytest]
markers =
    integration: hits live arXiv/PDF + requires PyMuPDF (network)
```

- [ ] **Step 4: Verify** — unit: `python -m pytest test_extract.py -v` (PASS). Integration: ensure fitz available (`python -m pip install pymupdf`), then `python -m pytest -m integration -v`. Mamba HTML test must pass. For the image-PDF test, confirm it does not crash and reports a coverage value. If PyMuPDF can't be installed locally, defer integration to the Docker image (Task 6) and note it.

- [ ] **Step 5: Commit**
```bash
git add extract.py test_extract.py pytest.ini
git commit -m "feat(pdf-extract): CLI + integration smokes"
```

---

## Task 6: Dockerfile + README

**Files:** Create `repo/skill/pdf-extract/Dockerfile`, `repo/skill/pdf-extract/README.md`

- [ ] **Step 1: Dockerfile**
```dockerfile
# build: docker build -t pdf-extract .   (run from this dir)
# run:   docker run --rm pdf-extract "<arXiv id | PDF URL>"
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN pip install pymupdf
COPY extract.py /app/extract.py
WORKDIR /app
ENTRYPOINT ["python", "extract.py"]
```

- [ ] **Step 2: Build + smoke**
```bash
cd repo/skill/pdf-extract
docker build -t pdf-extract .
docker run --rm pdf-extract "2312.00752"
docker run --rm pdf-extract "https://arxiv.org/pdf/2606.02437"
```
Expected: first → JSON `"source":"arxiv_html"`, `"references_count">0`, fulltext mentions state space; second → does not crash, reports a `coverage` (ideally `"none"` for the image PDF).

- [ ] **Step 3: README.md**
```markdown
# pdf-extract — full text + references (Mode C #2)

Extracts a paper's full text + reference list. **arXiv HTML first, text-layer PDF (PyMuPDF) second, no OCR.**

## Build & run
    cd skill/pdf-extract
    docker build -t pdf-extract .
    docker run --rm pdf-extract "<arXiv id | PDF URL>"
(Local: `pip install pymupdf` then `python extract.py "<id>"`.)

## Output (JSON)
`ok`, `source` (arxiv_html|pdf_textlayer|none), `coverage` (full|partial|none), `text_layer`,
`fulltext`, `fulltext_chars`, `references[]`, `references_count`, `notes`.

## How the skill uses it
Mode C 取文 runs it alongside `paper-verify`. `fulltext` → C2/C3 scans; `references` → `paper-verify --refs` for C1 hallucinated-reference detection.

## Limits (v1)
- **No OCR**: image/scanned PDFs → `coverage:"none"` (honest fall back, not a crash).
- No paywall bypass; no table/formula/figure structuring.
- Reference splitting from PDF text is heuristic (`references_count` reported; arXiv HTML refs are structured and cleaner).
```

- [ ] **Step 4: Commit**
```bash
git add Dockerfile README.md
git commit -m "feat(pdf-extract): Dockerfile + README"
```

---

## Task 7: `paper-verify --refs` — batch-resolve reference strings (completes C1)

**Files:** Modify `repo/skill/paper-verify/verify.py`, `repo/skill/paper-verify/test_verify.py`

- [ ] **Step 1: Failing test**
```python
def test_match_reference():
    assert verify.match_reference("Vaswani Attention is all you need 2017",
                                  "Attention Is All You Need") is True
    assert verify.match_reference("Totally unrelated string about cats",
                                  "Attention Is All You Need") is False

def test_resolve_refs(monkeypatch):
    # searcher returns a title for the real one, None for the fake
    def fake_search(ref):
        return "Attention Is All You Need" if "Vaswani" in ref else None
    out = verify.resolve_refs(["Vaswani Attention is all you need 2017",
                               "Nonexistent fabricated reference xyz 2099"],
                              searcher=fake_search)
    assert out["provided_checked"] == 2
    assert len(out["provided_unresolved"]) == 1
    assert "Nonexistent" in out["provided_unresolved"][0]
```

- [ ] **Step 2: Run, verify FAIL**

- [ ] **Step 3: Implement (append to verify.py; reuse existing `re`, `http_get_json`, `OPENALEX`, `MAILTO`)**
```python
import re as _re  # if re not already imported at top; otherwise reuse


def match_reference(ref, candidate_title):
    if not candidate_title:
        return False
    title_tokens = set(_re.findall(r"\w+", candidate_title.lower()))
    ref_tokens = set(_re.findall(r"\w+", (ref or "").lower()))
    if not title_tokens:
        return False
    overlap = len(title_tokens & ref_tokens) / len(title_tokens)
    return overlap >= 0.6


def _search_openalex_title(ref):
    import urllib.parse
    q = urllib.parse.quote(ref[:300])
    url = f"{OPENALEX}/works?search={q}&per_page=1&mailto={MAILTO}"
    try:
        data = http_get_json(url)
    except Exception:
        return None
    results = data.get("results") or []
    if not results:
        return None
    return results[0].get("title") or results[0].get("display_name")


def resolve_refs(refs, searcher=None):
    searcher = searcher or _search_openalex_title
    unresolved = []
    for ref in refs:
        title = searcher(ref)
        if not (title and match_reference(ref, title)):
            unresolved.append(ref)
    return {"provided_checked": len(refs), "provided_unresolved": unresolved}
```
Note: if `verify.py` imported `re` already at top, drop the `import re as _re` line and use `re.findall`. Check the top of the file and keep imports consistent (use whichever name is already there).

- [ ] **Step 4: Run, verify PASS** — `cd repo/skill/paper-verify && python -m pytest test_verify.py -k "reference or resolve_refs" -v`

- [ ] **Step 5: Wire `--refs` into the CLI** — replace the `__main__` block in verify.py with:
```python
if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(json.dumps({"resolved": False, "notes": ["usage: python verify.py <id> [--refs <file|->]"]}))
        sys.exit(0)
    refs = None
    if "--refs" in args:
        i = args.index("--refs")
        src = args[i + 1] if i + 1 < len(args) else "-"
        raw = sys.stdin.read() if src == "-" else open(src, encoding="utf-8").read()
        refs = json.loads(raw)
        args = args[:i] + args[i + 2:]
    result = verify(args[0])
    if refs is not None:
        rr = resolve_refs(refs)
        result.setdefault("references", {}).update(rr)
        result.setdefault("flags", {})["refs_unresolved"] = len(rr["provided_unresolved"])
    print(format_output(result))
```

- [ ] **Step 6: Verify CLI** — `echo '["Vaswani Attention is all you need 2017","fabricated xyz 2099"]' | python verify.py 10.1126/science.adi2336 --refs -` → JSON includes `references.provided_checked: 2` and `flags.refs_unresolved` ≥ 1 (the fabricated one). Re-run unit suite: `python -m pytest -v` all PASS.

- [ ] **Step 7: Commit**
```bash
cd /d/paper/hype_experiment_3/repo
git add skill/paper-verify/verify.py skill/paper-verify/test_verify.py
git commit -m "feat(paper-verify): --refs batch-resolve (completes Mode C C1)"
```

---

## Task 8: End-to-end + wire into skill

**Files:** Modify `repo/skill/SKILL.md`, `repo/skill/references/templates.md`

- [ ] **Step 1: End-to-end smoke (manual, network + fitz/Docker)**
Run pdf-extract on Mamba, pipe its references into paper-verify --refs:
```bash
cd /d/paper/hype_experiment_3/repo/skill
python pdf-extract/extract.py "2312.00752" > /tmp/mamba.json
python -c "import json;print(json.dumps(json.load(open('/tmp/mamba.json'))['references']))" | python paper-verify/verify.py "2312.00752" --refs -
```
Expected: paper-verify output has `references.provided_checked` > 0 and a `flags.refs_unresolved` count (Mamba's real refs should mostly resolve → unresolved low). Record the numbers. (If fitz/network unavailable locally, run the pdf-extract step via Docker.)

- [ ] **Step 2: SKILL.md — Mode C 取文** — find this exact line:
`- **結構化事實**:先跑 \`paper-verify "<DOI/arXiv/標題>"\`(skill/paper-verify/,Docker 或 \`python verify.py\`)→ 拿 facts+flags 餵 C1/C4/C5 與作者識別;\`resolved:false\`(太新未索引)→ 退回 WebFetch,**不當紅旗**。`
Append after it:
`- **全文與引用**:跑 \`pdf-extract "<arXiv id/PDF URL>"\`(skill/pdf-extract/)→ \`fulltext\` 餵 C2/C3 文字掃描;\`references\` 餵 \`paper-verify <id> --refs -\` 完成 C1 幻覺引用偵測。\`coverage:none\`(圖片化 PDF)→ C2/C3 標受限,同今。`

- [ ] **Step 3: Template F — C1 line** — find:
`- **C1 幻覺/不存在引用**：給定參考文獻清單 \`{refs}\`(過多時取樣 N 筆並回報「已查 N / 共 M」)。對每筆用 Crossref/DOI/arXiv 核對是否存在、標題-作者-年份是否吻合。回傳:\`已查/總數\`、\`確認不存在\` 筆數與清單、\`無法確認\` 筆數、一句總評。`
Replace with:
`- **C1 幻覺/不存在引用**：優先把 \`pdf-extract\` 抽到的 \`references\` 餵 \`paper-verify --refs\` → 用其 \`provided_unresolved\` 為「確認不存在/查無」依據(已查 N / 共 M);無 pdf-extract 時才手動抽樣 Crossref/arXiv 核對。回傳:\`已查/總數\`、\`確認不存在\` 筆數與清單、\`無法確認\` 筆數、一句總評。`

- [ ] **Step 4: Verify + commit**
```bash
cd /d/paper/hype_experiment_3/repo
grep -n "pdf-extract" skill/SKILL.md skill/references/templates.md
git add skill/SKILL.md skill/references/templates.md
git commit -m "feat(mode-c): wire pdf-extract into 取文 + Template F C1 via --refs"
```

---

## Task 9: Sync to live skill + final commit

**Files:** copy tool dir + paper-verify update + apply 2 markdown edits to live

- [ ] **Step 1: Copy to live**
```bash
mkdir -p "/c/Users/GMfatcat/.claude/skills/dissecting-paper-hype/pdf-extract"
cp /d/paper/hype_experiment_3/repo/skill/pdf-extract/extract.py /d/paper/hype_experiment_3/repo/skill/pdf-extract/Dockerfile /d/paper/hype_experiment_3/repo/skill/pdf-extract/README.md "/c/Users/GMfatcat/.claude/skills/dissecting-paper-hype/pdf-extract/"
cp /d/paper/hype_experiment_3/repo/skill/paper-verify/verify.py "/c/Users/GMfatcat/.claude/skills/dissecting-paper-hype/paper-verify/verify.py"
```
(test files + pytest.ini stay in repo only.)

- [ ] **Step 2: Apply the 2 markdown edits from Task 8 Steps 2–3 to the LIVE files** (`...\SKILL.md`, `...\references\templates.md`) using the same exact anchor strings. Do NOT whole-file copy (preserves live's Mode B absolute paths).

- [ ] **Step 3: Verify live**
```bash
ls "/c/Users/GMfatcat/.claude/skills/dissecting-paper-hype/pdf-extract/"
grep -rn "pdf-extract" "/c/Users/GMfatcat/.claude/skills/dissecting-paper-hype/SKILL.md"
```

- [ ] **Step 4: Final repo commit (local, NO push)**
```bash
cd /d/paper/hype_experiment_3/repo
git add -A
git commit -m "chore(pdf-extract): sync tool + paper-verify --refs + wiring to live"
git log --oneline -1 ; git status -sb | head -1
```

---

## Self-Review
- **Spec coverage:** §2 form→T1/T5/T6; §3 source priority (arXiv HTML→PDF→image none→fail)→T4 `extract()`; §4 fulltext+refs→T2/T3/T4; §5 output JSON→T4 `_result`/T5 `format_output`; §6 integration (composable, --refs)→T7 + T8; §7 files→all; §8 deps (PyMuPDF lazy, no tesseract)→T4 lazy import + T6 Dockerfile; §9 testing→unit T1–T4/T7 + integration T5/T6/T8. C1 completion (`paper-verify --refs`) explicitly built in T7.
- **Placeholder scan:** none. Image-PDF integration test uses a real URL (Mind Lab) and asserts no-crash + a coverage value (ideally none) — concrete, not vague. OCR is out-of-scope per spec, not a TODO.
- **Type/name consistency:** `detect_source` returns `(type, value)` used by `extract`; `_result(query, ok, source, coverage, text_layer, fulltext, refs, notes)` signature consistent across `_fail`/`_extract_pdf`/`extract`/tests; output keys (source/coverage/text_layer/fulltext/references/references_count/notes) consistent T4↔T5↔README. paper-verify `resolve_refs` returns `{provided_checked, provided_unresolved}` matching the `references` block + `flags.refs_unresolved` already defined in #1's compute_flags.
- **Dep-import safety:** `fitz` imported only inside `extract_pdf_text`; all unit tests (T1–T4, T7) avoid the PDF path via injection, so they run without PyMuPDF. Confirmed in T4 tests (inject `pdf_text=lambda b: ...`).
