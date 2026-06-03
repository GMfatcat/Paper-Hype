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
- **Reference extraction is best-effort.** Full text is reliable; references depend on the paper having a structured HTML bibliography or a clean numbered PDF reference list. `references_count` is reported; when low/0, Mode C treats C1 as 受限 and may sample manually. Robust parsing (GROBID-level) is out of scope.
