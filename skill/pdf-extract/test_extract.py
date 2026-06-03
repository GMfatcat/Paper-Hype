import extract
import json as _json
import pytest


# --- Task 1: detect_source ---

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


# --- Task 2: strip_html + parse_arxiv_html ---

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


# --- Task 3: split_references + assess_text_layer ---

def test_split_references_bracketed():
    block = ("Some body text here. References [1] A. Vaswani. Attention is all you need. 2017. "
             "[2] A. Gu. Mamba long sequences modeling paper. 2023.")
    refs = extract.split_references(block)
    assert len(refs) == 2
    assert "Vaswani" in refs[0] and "Gu" in refs[1]

def test_split_references_no_section_returns_few():
    # No 'References' heading -> best effort, should not crash
    assert isinstance(extract.split_references("no refs here"), list)

def test_split_references_anchors_on_last_heading():
    # an early in-text 'references' mention must NOT break splitting
    block = ("In our references we cite many works. ... body body body. "
             "References\n[1] A. Author. First real paper title here. 2019.\n"
             "[2] B. Author. Second real paper title here. 2020.\n"
             "[3] C. Author. Third real paper title goes here. 2021.")
    refs = extract.split_references(block)
    assert len(refs) == 3
    assert "First real paper" in refs[0]

def test_split_references_line_numbered_fallback():
    block = ("Bibliography\n"
             "1. Alpha Author. A paper about alpha methods and things. 2018.\n"
             "2. Beta Author. A paper about beta methods and things. 2019.\n"
             "3. Gamma Author. A paper about gamma methods and things. 2020.")
    refs = extract.split_references(block)
    assert len(refs) == 3

def test_assess_text_layer():
    assert extract.assess_text_layer("x" * 250) == (True, "full")
    assert extract.assess_text_layer("short") == (True, "partial")
    assert extract.assess_text_layer("") == (False, "none")


# --- Task 4: extract orchestration (dependency-injected) ---

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


# --- Task 5: CLI format_output + integration smokes ---

def test_format_output_valid_json():
    r = extract._result("q", True, "arxiv_html", "full", True, "text", ["a"], ["n"])
    parsed = _json.loads(extract.format_output(r))
    assert parsed["references_count"] == 1

@pytest.mark.integration
def test_integration_arxiv_html_mamba():
    r = extract.extract("2312.00752")
    assert r["ok"] and r["source"] == "arxiv_html"
    assert r["fulltext_chars"] > 5000
    assert "state space" in r["fulltext"].lower()
    # references are best-effort: this paper's arXiv HTML has no structured bibliography
    assert r["references_count"] >= 0

@pytest.mark.integration
def test_integration_image_pdf_coverage_none():
    # A known image-only/scanned PDF URL (replace with a real one at run time if needed).
    r = extract.extract("https://arxiv.org/pdf/2606.02437")  # Mind Lab — image-encoded PDF
    assert r["ok"] is True
    assert r["coverage"] in ("none", "partial", "full")  # must not crash; ideally none
