import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from html import unescape

_TEI = "{http://www.tei-c.org/ns/1.0}"

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


def split_references(text):
    text = text or ""
    matches = list(re.finditer(r'(?im)^\s*(references|bibliography)\s*$', text))
    if not matches:
        matches = list(re.finditer(r'(?i)\b(references|bibliography)\b', text))
    tail = text[matches[-1].end():] if matches else text
    parts = re.split(r'(?m)(?:^|\s)\[\d+\]\s*', tail)
    entries = [re.sub(r'\s+', ' ', p).strip() for p in parts]
    entries = [e for e in entries if len(e) > 25]
    if len(entries) >= 3:
        return entries
    parts2 = re.split(r'(?m)^\s*\d{1,3}[.\)]\s+', tail)
    entries2 = [re.sub(r'\s+', ' ', p).strip() for p in parts2]
    entries2 = [e for e in entries2 if len(e) > 25]
    return entries2 if len(entries2) > len(entries) else entries


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


def assess_text_layer(text, threshold=TEXT_LAYER_MIN):
    n = len((text or "").strip())
    if n >= threshold:
        return True, "full"
    if n > 0:
        return True, "partial"
    return False, "none"


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


def _result(query, ok, source, coverage, text_layer, fulltext, refs, notes, references_source="none"):
    refs = [c for c in (clean_reference(r) for r in (refs or [])) if c]
    return {
        "query": query, "ok": ok, "source": source, "coverage": coverage,
        "text_layer": text_layer, "fulltext": fulltext, "fulltext_chars": len(fulltext or ""),
        "references": refs, "references_count": len(refs), "references_source": references_source,
        "notes": notes,
    }


def _fail(query, msg):
    return _result(query, False, "none", "none", False, "", [], [msg])


def _refs_via_grobid_or_regex(pdf_bytes, text_for_regex, grobid_fn, grobid_url):
    if grobid_url and pdf_bytes is not None:
        g = grobid_fn(pdf_bytes, grobid_url)
        if g:
            return g, "grobid"
    if text_for_regex:
        return split_references(text_for_regex), "regex_fallback"
    return [], "none"


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


def format_output(result):
    return json.dumps(result, ensure_ascii=False, indent=2)


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
