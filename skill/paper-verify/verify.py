import json
import os
import re
import sys
import urllib.error
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
        # unknown works_count (None) is NOT weak — avoid false-flagging real authors
        # whose ORCID/works OpenAlex simply lacks (e.g. large industry teams).
        return (not a.get("orcid")) and (wc is not None and wc <= WEAK_WORKS)
    weak_n = sum(1 for a in authors if weak(a))
    ratio = (weak_n / n) if n else 0.0
    venue = facts.get("venue") or {}
    vtype = venue.get("type")
    wl_hit = (venue.get("watchlist") or {})
    wl_cat = wl_hit.get("category")
    return {
        "retracted": bool(facts.get("retraction", {}).get("is_retracted")),
        "not_in_doaj_journal": vtype == "journal" and venue.get("is_in_doaj") is False,
        "venue_repository_only": vtype == "repository",
        "venue_predatory": wl_cat == "predatory",
        "venue_hijacked": wl_cat == "hijacked",
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
                      "venue_repository_only": False, "venue_predatory": False,
                      "venue_hijacked": False, "author_identity_weak": False,
                      "author_weak_ratio": 0.0, "work_not_found": True, "refs_unresolved": 0},
            "notes": ["not found in OpenAlex — likely too new / not yet indexed; fall back to WebFetch checks"],
        }
    facts = extract_facts(work)
    facts["authors"] = enrich_authors(facts["authors"])
    facts["venue"]["watchlist"] = match_venue(facts.get("venue"), _get_watchlists())
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


# ---------------------------------------------------------------------------
# Pure helpers (no network)
# ---------------------------------------------------------------------------

_DOI_RE = re.compile(r'10\.\d{4,}/[^\s"<>]+')

def extract_doi(ref):
    if not ref:
        return None
    m = _DOI_RE.search(ref)
    return m.group(0).rstrip('.,;)]}>') if m else None

def _ref_year(ref):
    m = re.search(r'\b(19|20)\d{2}\b', ref or "")
    return m.group(0) if m else None

def _overlap(title, ref):
    tt = set(re.findall(r"\w+", (title or "").lower()))
    rt = set(re.findall(r"\w+", (ref or "").lower()))
    return (len(tt & rt) / len(tt)) if tt else 0.0

def match_any(ref, candidates):
    rt = set(re.findall(r"\w+", (ref or "").lower()))
    for c in candidates or []:
        title = c.get("title") or ""
        ttoks = re.findall(r"\w+", title.lower())
        n = len(ttoks)
        if 0 < n <= 4:                      # short title: require ALL title tokens present
            if set(ttoks) <= rt:
                return True
            continue
        if _overlap(title, ref) >= 0.6:
            return True
    return False

def _parse_candidates(data):
    out = []
    for it in ((data.get("message") or {}).get("items") or []):
        titles = it.get("title") or []
        if not titles:
            continue
        parts = ((it.get("issued") or {}).get("date-parts") or [[None]])
        year = str(parts[0][0]) if (parts and parts[0] and parts[0][0]) else None
        out.append({"title": titles[0], "year": year})
    return out


# ---------------------------------------------------------------------------
# C5 venue watchlists (predatory / hijacked) — pure helpers
# ---------------------------------------------------------------------------

def _norm_name(s):
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    if s.startswith("the "):
        s = s[4:]
    return re.sub(r"\s+", " ", s)

def _norm_issn(s):
    if not s:
        return None
    raw = re.sub(r"[^0-9xX]", "", s).upper()
    if len(raw) != 8 or not re.fullmatch(r"\d{7}[\dX]", raw):
        return None
    return raw[:4] + "-" + raw[4:]


DEFAULT_WATCHLISTS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "data", "watchlists.json")

_WATCHLISTS_CACHE = None

def _get_watchlists():
    global _WATCHLISTS_CACHE
    if _WATCHLISTS_CACHE is None:
        _WATCHLISTS_CACHE = load_watchlists()
    return _WATCHLISTS_CACHE

def load_watchlists(path=DEFAULT_WATCHLISTS):
    empty = {"issn": {}, "name": {}, "publisher": {},
             "meta": {"note": "watchlists unavailable"}, "entries": {}}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return empty
    issn_idx, name_idx, pub_idx, entries = {}, {}, {}, {}
    def add_journals(section, category):
        for e in data.get(section) or []:
            nm = _norm_name(e.get("name"))
            if nm:
                name_idx.setdefault(nm, category)
                entries[(category, "name", nm)] = e
            for raw in e.get("issn") or []:
                iss = _norm_issn(raw)
                if iss:
                    issn_idx.setdefault(iss, category)
                    entries[(category, "issn", iss)] = e
    add_journals("hijacked_journals", "hijacked")
    add_journals("predatory_journals", "predatory")
    for e in data.get("predatory_publishers") or []:
        nm = _norm_name(e.get("name"))
        if nm:
            pub_idx.setdefault(nm, "predatory")
            entries[("predatory", "publisher", nm)] = e
    return {"issn": issn_idx, "name": name_idx, "publisher": pub_idx,
            "meta": data.get("meta") or {}, "entries": entries}


def match_venue(venue, watchlists):
    venue = venue or {}
    issns = [i for i in (_norm_issn(x) for x in (venue.get("issn") or [])) if i]
    nm = _norm_name(venue.get("name"))
    pub = _norm_name(venue.get("publisher"))
    meta = watchlists.get("meta") or {}
    src = (meta.get("sources") or {})
    sd = meta.get("snapshot_date")

    def hit(category, matched_by, value, list_name):
        return {"category": category, "list": list_name, "matched_by": matched_by,
                "value": value, "source": src.get(list_name), "snapshot_date": sd}

    for iss in issns:
        if watchlists["issn"].get(iss) == "hijacked":
            return hit("hijacked", "issn", iss, "hijacked_journals")
    if nm and watchlists["name"].get(nm) == "hijacked":
        return hit("hijacked", "name", nm, "hijacked_journals")
    for iss in issns:
        if watchlists["issn"].get(iss) == "predatory":
            return hit("predatory", "issn", iss, "predatory_journals")
    if nm and watchlists["name"].get(nm) == "predatory":
        return hit("predatory", "name", nm, "predatory_journals")
    if pub and watchlists["publisher"].get(pub) == "predatory":
        return hit("predatory", "publisher", pub, "predatory_publishers")
    return None


# ---------------------------------------------------------------------------
# Network seams (injectable for testing)
# ---------------------------------------------------------------------------

def _doi_exists(doi, timeout=30):
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi)}?mailto={MAILTO}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": f"paper-verify/1.0 (mailto:{MAILTO})"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return 200 <= r.status < 300
    except urllib.error.HTTPError as e:
        return False if e.code == 404 else None
    except Exception:
        return None

def _search_reference_candidates(ref, rows=5, timeout=30):
    q = urllib.parse.quote(ref[:400])
    url = f"https://api.crossref.org/works?query.bibliographic={q}&rows={rows}&mailto={MAILTO}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": f"paper-verify/1.0 (mailto:{MAILTO})",
                                                   "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return _parse_candidates(json.loads(r.read().decode("utf-8")))
    except Exception:
        return []


def _search_reference_openalex(ref, timeout=30):
    # Second resolver: OpenAlex search-by-title for refs Crossref query.bibliographic missed.
    q = urllib.parse.quote((ref or "")[:400])
    url = f"{OPENALEX}/works?search={q}&per_page=1&mailto={MAILTO}"
    try:
        data = http_get_json(url, timeout=timeout)
    except Exception:
        return []
    out = []
    for w in (data.get("results") or []):
        title = w.get("display_name") or w.get("title")
        if not title:
            continue
        yr = w.get("publication_year")
        out.append({"title": title, "year": str(yr) if yr else None})
    return out


# ---------------------------------------------------------------------------
# Legacy single-title searcher (kept for backward compat; _search_reference_title)
# ---------------------------------------------------------------------------

def _search_reference_title(ref):
    # Crossref query.bibliographic is purpose-built for matching messy reference strings
    q = urllib.parse.quote(ref[:400])
    url = f"https://api.crossref.org/works?query.bibliographic={q}&rows=1&mailto={MAILTO}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": f"paper-verify/1.0 (mailto:{MAILTO})",
                                                   "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    items = (data.get("message") or {}).get("items") or []
    if not items:
        return None
    titles = items[0].get("title") or []
    return titles[0] if titles else None


def resolve_refs(refs, candidate_fetcher=None, doi_checker=None, oa_fetcher=None):
    candidate_fetcher = candidate_fetcher or _search_reference_candidates
    doi_checker = doi_checker or _doi_exists
    oa_fetcher = oa_fetcher or _search_reference_openalex
    unresolved = []
    for ref in refs:
        doi = extract_doi(ref)
        if doi and doi_checker(doi) is True:
            continue  # DOI confirmed to exist -> resolved
        if match_any(ref, (candidate_fetcher(ref) or [])[:1]):
            continue  # Crossref query.bibliographic top-1
        if match_any(ref, (oa_fetcher(ref) or [])[:1]):
            continue  # second resolver: OpenAlex search-by-title (only on Crossref miss)
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
