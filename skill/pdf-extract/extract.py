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


def format_output(result):
    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # JSON is UTF-8; avoid Windows cp950 crash
    except Exception:
        pass
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "notes": ["usage: python extract.py <arXiv id | PDF URL>"]}))
        sys.exit(0)
    print(format_output(extract(sys.argv[1])))
