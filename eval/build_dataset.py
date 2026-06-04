# build_dataset.py  — run: python build_dataset.py
import json, os, re, urllib.parse, urllib.request

HERE = os.path.dirname(__file__)
DATADIR = os.path.join(HERE, "datasets")
MAILTO = "paper-verify@example.org"

# Real DOIs whose Crossref reference lists supply REAL refs (these papers exist & have refs in Crossref):
REAL_SOURCE_DOIS = [
    "10.1126/science.adi2336", "10.1038/s41586-021-03819-2",
    "10.1056/NEJMoa2034577", "10.1016/j.cell.2021.04.048",
    "10.1145/3442188.3445922",
]

def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": f"eval (mailto:{MAILTO})"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))

def real_refs_from_crossref(doi, limit=40):
    data = _get_json(f"https://api.crossref.org/works/{urllib.parse.quote(doi)}?mailto={MAILTO}")
    refs = []
    for r in (data.get("message", {}).get("reference") or [])[:limit]:
        title = r.get("article-title") or r.get("volume-title") or r.get("unstructured")
        author = r.get("author", "")
        year = r.get("year", "")
        s = " ".join(x for x in [author, title, year] if x).strip()
        if title and len(s) > 15:
            refs.append(s)
    return refs

def perturb(ref):
    # mutate a real ref into a non-existent one (swap title words, bump year)
    words = ref.split()
    words = ["Quantized" if w.istitle() else w for w in words][:1] + words[1:]
    ref2 = re.sub(r"\b(19|20)\d{2}\b", "2099", ref)
    return "Nonexistent Synthetic " + ref2  # clearly synthetic prefix

def build_c1():
    real, seen = [], set()
    for doi in REAL_SOURCE_DOIS:
        try:
            for s in real_refs_from_crossref(doi):
                if s not in seen:
                    seen.add(s); real.append(s)
        except Exception as e:
            print("skip", doi, e)
    fakes = [perturb(s) for s in real[:120]]  # perturbed-real fakes (clearly synthetic)
    rows = [{"ref": s, "label": "real"} for s in real] + [{"ref": s, "label": "fake"} for s in fakes]
    with open(os.path.join(DATADIR, "c1_references.jsonl"), "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"c1: {len(real)} real, {len(fakes)} fake")

def fetch_citeaudit():
    # best-effort: try known locations; on failure, note and skip
    candidates = [
        "https://raw.githubusercontent.com/checkcitation/citeaudit/main/benchmark.jsonl",
    ]
    for url in candidates:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "eval"})
            with urllib.request.urlopen(req, timeout=60) as r:
                open(os.path.join(DATADIR, "c1_citeaudit.jsonl"), "wb").write(r.read())
            print("CiteAudit fetched:", url); return True
        except Exception as e:
            print("CiteAudit fetch failed:", url, e)
    print("CiteAudit not fetched — using self-built C1 only")
    return False

if __name__ == "__main__":
    os.makedirs(DATADIR, exist_ok=True)
    fetch_citeaudit()
    build_c1()
