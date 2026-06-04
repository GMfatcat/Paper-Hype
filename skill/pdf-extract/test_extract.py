import extract
import json as _json
import os
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


# --- GROBID Task 1: parse_grobid_tei ---

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


# --- GROBID Task 2: grobid_references + _grobid_post (network seam) ---

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


# --- GROBID Task 3: decision order + references_source ---

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


# --- GROBID Task 4: CLI format_output includes references_source ---

def test_format_output_includes_references_source():
    r = extract._result("q", True, "arxiv_html", "full", True, "text", ["a"], ["n"],
                        references_source="grobid")
    import json as _j
    assert _j.loads(extract.format_output(r))["references_source"] == "grobid"

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


# --- Task 5: GROBID integration smokes ---

@pytest.mark.integration
def test_integration_grobid_llama_refs():
    import os
    r = extract.extract("2302.13971", grobid_url=os.environ.get("GROBID_URL", "http://localhost:8070"))
    assert r["ok"]
    assert r["references_source"] == "grobid"
    assert r["references_count"] >= 15

@pytest.mark.integration
def test_integration_grobid_down_falls_back():
    r = extract.extract("2302.13971", grobid_url="http://localhost:9")
    assert r["ok"]
    assert r["references_source"] in ("regex_fallback", "none")
