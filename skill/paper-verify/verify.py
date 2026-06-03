import json
import re
import sys
import urllib.parse
import urllib.request

OPENALEX = "https://api.openalex.org"
MAILTO = "paper-verify@example.org"
MIN_AUTHORS = 5
WEAK_RATIO = 0.6
WEAK_WORKS = 1


def build_openalex_url(identifier):
    ident = (identifier or "").strip()
    low = ident.lower()
    if low.startswith("10.") or "doi.org/" in low:
        doi = ident.split("doi.org/")[-1]
        return f"{OPENALEX}/works/https://doi.org/{doi}?mailto={MAILTO}"
    arx = low.replace("arxiv:", "").strip()
    if len(arx) >= 9 and arx[:4].isdigit() and "." in arx and "/" not in arx and " " not in arx:
        return f"{OPENALEX}/works/https://doi.org/10.48550/arXiv.{arx}?mailto={MAILTO}"
    q = urllib.parse.quote(ident)
    return f"{OPENALEX}/works?search={q}&per_page=1&mailto={MAILTO}"


def extract_facts(work):
    src = ((work.get("primary_location") or {}).get("source")) or {}
    authors = []
    for a in work.get("authorships", []):
        au = a.get("author") or {}
        orcid = au.get("orcid")
        insts = a.get("institutions") or []
        authors.append({
            "name": au.get("display_name"),
            "orcid": orcid.replace("https://orcid.org/", "") if orcid else None,
            "orcid_verified": None,           # filled by enrich_authors (network)
            "works_count": None,              # filled by enrich_authors for no-ORCID authors
            "openalex_author_id": au.get("id"),
            "institution": insts[0].get("display_name") if insts else None,
        })
    return {
        "openalex_id": work.get("id"),
        "title": work.get("title") or work.get("display_name"),
        "retraction": {"is_retracted": bool(work.get("is_retracted")), "note": ""},
        "venue": {
            "name": src.get("display_name"),
            "type": src.get("type"),
            "is_in_doaj": src.get("is_in_doaj"),
            "publisher": src.get("host_organization_name"),
            "issn": src.get("issn") or [],
        },
        "authors": authors,
        "references": {
            "referenced_works_count": len(work.get("referenced_works") or []),
            "cited_by_count": work.get("cited_by_count"),
            "provided_checked": 0,
            "provided_unresolved": [],
        },
    }


def compute_flags(facts):
    authors = facts.get("authors") or []
    n = len(authors)
    def weak(a):
        wc = a.get("works_count")
        return (not a.get("orcid")) and (wc is None or wc <= WEAK_WORKS)
    weak_n = sum(1 for a in authors if weak(a))
    ratio = (weak_n / n) if n else 0.0
    venue = facts.get("venue") or {}
    vtype = venue.get("type")
    return {
        "retracted": bool(facts.get("retraction", {}).get("is_retracted")),
        "not_in_doaj_journal": vtype == "journal" and venue.get("is_in_doaj") is False,
        "venue_repository_only": vtype == "repository",
        "author_identity_weak": n >= MIN_AUTHORS and ratio >= WEAK_RATIO,
        "author_weak_ratio": round(ratio, 2),
        "work_not_found": False,
        "refs_unresolved": len(facts.get("references", {}).get("provided_unresolved") or []),
    }


def http_get_json(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": f"paper-verify (mailto:{MAILTO})",
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_openalex(identifier):
    try:
        data = http_get_json(build_openalex_url(identifier))
    except Exception:
        return None
    if isinstance(data, dict) and "results" in data:
        results = data.get("results") or []
        return results[0] if results else None
    return data


def fetch_orcid_exists(orcid, timeout=20):
    if not orcid:
        return False
    oid = orcid.rstrip("/").split("/")[-1]
    try:
        req = urllib.request.Request(f"https://pub.orcid.org/v3.0/{oid}/person",
                                     headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


def enrich_authors(authors):
    # confirm ORCIDs; for no-ORCID authors fetch works_count via /authors/{id}
    for a in authors:
        if a.get("orcid"):
            a["orcid_verified"] = fetch_orcid_exists(a["orcid"])
        elif a.get("openalex_author_id"):
            try:
                au = http_get_json(f"{a['openalex_author_id']}?mailto={MAILTO}")
                a["works_count"] = au.get("works_count")
            except Exception:
                a["works_count"] = None
    return authors


def verify(identifier):
    work = fetch_openalex(identifier)
    if work is None:
        return {
            "query": identifier, "resolved": False, "openalex_id": None, "title": None,
            "retraction": {"is_retracted": False, "note": ""}, "venue": {}, "authors": [],
            "references": {"referenced_works_count": None, "cited_by_count": None,
                           "provided_checked": 0, "provided_unresolved": []},
            "flags": {"retracted": False, "not_in_doaj_journal": False,
                      "venue_repository_only": False, "author_identity_weak": False,
                      "author_weak_ratio": 0.0, "work_not_found": True, "refs_unresolved": 0},
            "notes": ["not found in OpenAlex — likely too new / not yet indexed; fall back to WebFetch checks"],
        }
    facts = extract_facts(work)
    facts["authors"] = enrich_authors(facts["authors"])
    flags = compute_flags(facts)
    result = {"query": identifier, "resolved": True}
    result.update(facts)
    result["flags"] = flags
    result["notes"] = ["resolved via OpenAlex"]
    return result


def match_reference(ref, candidate_title):
    if not candidate_title:
        return False
    title_tokens = set(re.findall(r"\w+", candidate_title.lower()))
    ref_tokens = set(re.findall(r"\w+", (ref or "").lower()))
    if not title_tokens:
        return False
    overlap = len(title_tokens & ref_tokens) / len(title_tokens)
    return overlap >= 0.6


def _search_openalex_title(ref):
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


def format_output(result):
    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
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
