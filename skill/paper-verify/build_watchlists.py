"""Regenerate skill/paper-verify/data/watchlists.json from public sources.

Reproducible: snapshot_date is passed in (no hidden clock). If a source can't be
fetched, the prior section is kept (no silent truncation); meta.refreshed lists
which sections were actually updated this run.

Usage:
    python build_watchlists.py 2026-06-05        # date is required, explicit
Network-dependent; run manually as the refresh step.
"""
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "watchlists.json")
SOURCES = {
    "predatory_journals": "https://beallslist.net/standalone-journals/",
    "predatory_publishers": "https://beallslist.net/",
    "hijacked_journals": "https://retractionwatch.com/the-retraction-watch-hijacked-journal-checker/",
}
_UA = {"User-Agent": "paper-verify watchlist builder (mailto:paper-verify@example.org)"}


def fetch(url, timeout=60):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def parse_beall_journals(html):
    names = re.findall(r"<li>\s*<a[^>]*>(.*?)</a>", html, re.I | re.S)
    out = []
    for n in names:
        n = re.sub(r"<[^>]+>", "", n).strip()
        if n:
            out.append({"name": n, "issn": []})
    return out or None


def parse_beall_publishers(html):
    names = re.findall(r"<li>\s*<a[^>]*>(.*?)</a>", html, re.I | re.S)
    out = []
    for n in names:
        n = re.sub(r"<[^>]+>", "", n).strip()
        if n:
            out.append({"name": n})
    return out or None


def parse_hijacked(html):
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.I | re.S)
    out = []
    for row in rows:
        cells = [re.sub(r"<[^>]+>", "", c).strip()
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.I | re.S)]
        if not cells:
            continue
        name = cells[0]
        issns = re.findall(r"\d{4}-\d{3}[\dxX]", row)
        if name:
            out.append({"name": name, "issn": issns})
    return out or None


def merge_sections(prior, predatory_journals, predatory_publishers,
                   hijacked_journals, snapshot_date):
    refreshed = []
    result = {"meta": dict(prior.get("meta") or {})}
    sections = {
        "predatory_journals": predatory_journals,
        "predatory_publishers": predatory_publishers,
        "hijacked_journals": hijacked_journals,
    }
    for key, fetched in sections.items():
        if fetched is None:
            result[key] = prior.get(key) or []
        else:
            result[key] = fetched
            refreshed.append(key)
    result["meta"]["snapshot_date"] = snapshot_date
    result["meta"]["sources"] = SOURCES
    result["meta"]["refreshed"] = refreshed
    result["meta"].setdefault(
        "note", "Beall's List is community-maintained and contested. A hit is a lead, not a verdict.")
    return result


def main(snapshot_date):
    try:
        with open(OUT, encoding="utf-8") as f:
            prior = json.load(f)
    except Exception:
        prior = {}
    def safe(parser, key):
        try:
            return parser(fetch(SOURCES[key]))
        except Exception as e:
            print("WARN could not refresh", key, "->", e)
            return None
    merged = merge_sections(
        prior,
        safe(parse_beall_journals, "predatory_journals"),
        safe(parse_beall_publishers, "predatory_publishers"),
        safe(parse_hijacked, "hijacked_journals"),
        snapshot_date,
    )
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print("WROTE", OUT, "refreshed:", merged["meta"]["refreshed"])


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if len(sys.argv) < 2:
        print("usage: python build_watchlists.py <YYYY-MM-DD>")
        sys.exit(2)
    main(sys.argv[1])
