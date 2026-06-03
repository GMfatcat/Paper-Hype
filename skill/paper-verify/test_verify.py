import json as _json
import subprocess
import sys
import pytest
import verify


# ---------------------------------------------------------------------------
# Task 1: build_openalex_url
# ---------------------------------------------------------------------------

def test_build_url_doi():
    u = verify.build_openalex_url("10.1126/science.adi2336")
    assert u.startswith("https://api.openalex.org/works/https://doi.org/10.1126/science.adi2336")
    assert "mailto=" in u

def test_build_url_doi_full_link():
    u = verify.build_openalex_url("https://doi.org/10.1016/S0140-6736(20)31180-6")
    assert "/works/https://doi.org/10.1016/S0140-6736(20)31180-6" in u

def test_build_url_arxiv():
    assert "/works/https://doi.org/10.48550/arXiv.2212.12794" in verify.build_openalex_url("arXiv:2212.12794")
    assert "/works/https://doi.org/10.48550/arXiv.2606.02437" in verify.build_openalex_url("2606.02437")

def test_build_url_title_search():
    u = verify.build_openalex_url("Attention Is All You Need")
    assert "/works?search=Attention" in u and "per_page=1" in u


# ---------------------------------------------------------------------------
# Task 2: extract_facts
# ---------------------------------------------------------------------------

CLEAN_WORK = {
    "id": "https://openalex.org/W123",
    "title": "GraphCast",
    "is_retracted": False,
    "cited_by_count": 1051,
    "referenced_works": ["https://openalex.org/W1", "https://openalex.org/W2"],
    "primary_location": {"source": {
        "display_name": "Science", "type": "journal", "is_in_doaj": False,
        "host_organization_name": "AAAS", "issn": ["0036-8075"]}},
    "authorships": [
        {"author": {"display_name": "Remi Lam", "orcid": "https://orcid.org/0000-0001-0000-0001"},
         "institutions": [{"display_name": "DeepMind"}]},
        {"author": {"display_name": "A. N. Other", "orcid": None}, "institutions": []},
    ],
}

def test_extract_facts_basic():
    f = verify.extract_facts(CLEAN_WORK)
    assert f["title"] == "GraphCast"
    assert f["retraction"]["is_retracted"] is False
    assert f["venue"]["name"] == "Science"
    assert f["venue"]["type"] == "journal"
    assert f["venue"]["is_in_doaj"] is False
    assert f["references"]["referenced_works_count"] == 2
    assert f["references"]["cited_by_count"] == 1051
    assert f["authors"][0]["orcid"] == "0000-0001-0000-0001"
    assert f["authors"][0]["institution"] == "DeepMind"
    assert f["authors"][1]["orcid"] is None


# ---------------------------------------------------------------------------
# Task 3: compute_flags
# ---------------------------------------------------------------------------

def _facts(authors=None, is_retracted=False, vtype="journal", in_doaj=True):
    return {
        "retraction": {"is_retracted": is_retracted, "note": ""},
        "venue": {"type": vtype, "is_in_doaj": in_doaj, "publisher": "X"},
        "authors": authors if authors is not None else [
            {"orcid": "0000-1", "works_count": 30}, {"orcid": "0000-2", "works_count": 5}],
        "references": {"provided_unresolved": []},
    }

def test_flag_retracted():
    assert verify.compute_flags(_facts(is_retracted=True))["retracted"] is True

def test_flag_not_in_doaj_journal():
    assert verify.compute_flags(_facts(in_doaj=False))["not_in_doaj_journal"] is True

def test_flag_repo_only():
    assert verify.compute_flags(_facts(vtype="repository"))["venue_repository_only"] is True

def test_flag_author_identity_weak():
    weak = [{"orcid": None, "works_count": 0} for _ in range(5)] + [{"orcid": "0000-9", "works_count": 12}]
    fl = verify.compute_flags(_facts(authors=weak))
    assert fl["author_identity_weak"] is True
    assert fl["author_weak_ratio"] >= 0.6

def test_flag_clean_all_false():
    fl = verify.compute_flags(_facts())
    assert not any([fl["retracted"], fl["not_in_doaj_journal"], fl["author_identity_weak"]])

def test_flag_small_team_not_weak():
    # 2 no-ORCID authors but team < MIN_AUTHORS -> not flagged
    fl = verify.compute_flags(_facts(authors=[{"orcid": None, "works_count": 0},
                                              {"orcid": None, "works_count": 0}]))
    assert fl["author_identity_weak"] is False


# ---------------------------------------------------------------------------
# Task 4: network layer (monkeypatched — no real network)
# ---------------------------------------------------------------------------

def test_fetch_openalex_unwraps_search(monkeypatch):
    # search responses have {"results": [...]}; single-work responses don't
    monkeypatch.setattr(verify, "http_get_json", lambda url, timeout=30: {"results": [{"id": "W1"}]})
    assert verify.fetch_openalex("some title")["id"] == "W1"
    monkeypatch.setattr(verify, "http_get_json", lambda url, timeout=30: {"id": "W2"})
    assert verify.fetch_openalex("10.1/x")["id"] == "W2"

def test_fetch_openalex_returns_none_on_error(monkeypatch):
    def boom(url, timeout=30):
        raise RuntimeError("404")
    monkeypatch.setattr(verify, "http_get_json", boom)
    assert verify.fetch_openalex("10.1/x") is None

def test_fetch_openalex_empty_search(monkeypatch):
    monkeypatch.setattr(verify, "http_get_json", lambda url, timeout=30: {"results": []})
    assert verify.fetch_openalex("no such title") is None


# ---------------------------------------------------------------------------
# Task 5: verify() orchestration
# ---------------------------------------------------------------------------

def test_verify_not_found(monkeypatch):
    monkeypatch.setattr(verify, "fetch_openalex", lambda i: None)
    r = verify.verify("2606.99999")
    assert r["resolved"] is False
    assert r["flags"]["work_not_found"] is True
    assert "too new" in " ".join(r["notes"]).lower() or "not" in " ".join(r["notes"]).lower()

def test_verify_resolved(monkeypatch):
    monkeypatch.setattr(verify, "fetch_openalex", lambda i: CLEAN_WORK)
    monkeypatch.setattr(verify, "enrich_authors", lambda authors: authors)  # skip network
    r = verify.verify("10.1126/science.adi2336")
    assert r["resolved"] is True
    assert r["title"] == "GraphCast"
    assert r["flags"]["retracted"] is False
    assert "openalex" in " ".join(r["notes"]).lower()


# ---------------------------------------------------------------------------
# Task 6: CLI / format_output + integration smokes
# ---------------------------------------------------------------------------

def test_cli_outputs_json(monkeypatch):
    # format_output must produce parseable JSON with required keys
    r = {"query": "x", "resolved": False, "flags": {"work_not_found": True}, "notes": []}
    out = verify.format_output(r)
    parsed = _json.loads(out)
    assert parsed["resolved"] is False

@pytest.mark.integration
def test_integration_retracted():
    r = verify.verify("10.1016/S0140-6736(20)31180-6")  # Surgisphere/Lancet, retracted
    assert r["resolved"] is True
    assert r["flags"]["retracted"] is True

@pytest.mark.integration
def test_integration_clean():
    r = verify.verify("10.1126/science.adi2336")  # GraphCast
    assert r["resolved"] is True
    assert r["flags"]["retracted"] is False
    assert r["venue"]["name"]  # has a venue
