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

def test_flag_unknown_works_not_weak():
    # 6 no-ORCID authors with UNKNOWN works_count (None) -> must NOT be flagged
    # (avoids false positives on large real teams OpenAlex lacks ORCID/works data for)
    authors = [{"orcid": None, "works_count": None} for _ in range(6)]
    fl = verify.compute_flags(_facts(authors=authors))
    assert fl["author_identity_weak"] is False
    assert fl["author_weak_ratio"] == 0.0


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


# ---------------------------------------------------------------------------
# Task 7: match_reference + resolve_refs
# ---------------------------------------------------------------------------

def test_match_reference():
    assert verify.match_reference("Vaswani Attention is all you need 2017",
                                  "Attention Is All You Need") is True
    assert verify.match_reference("Totally unrelated string about cats",
                                  "Attention Is All You Need") is False

def test_resolve_refs(monkeypatch):
    # no-DOI refs: candidate_fetcher returns a matching candidate for the real one, nothing for the fake
    def fake_fetch(ref):
        return [{"title": "Attention Is All You Need", "year": "2017"}] if "Vaswani" in ref else []
    out = verify.resolve_refs(
        ["Vaswani Attention is all you need 2017",
         "Nonexistent fabricated reference xyz 2099"],
        candidate_fetcher=fake_fetch, doi_checker=lambda d: None)
    assert out["provided_checked"] == 2
    assert out["provided_unresolved"] == ["Nonexistent fabricated reference xyz 2099"]


# ---------------------------------------------------------------------------
# Task 1 (C5): watchlist normalizers + loader
# ---------------------------------------------------------------------------

def test_norm_name():
    assert verify._norm_name("The Lancet!") == "lancet"
    assert verify._norm_name("  Nucleic   Acids  Research ") == "nucleic acids research"
    assert verify._norm_name("Bio-Medical & Eng.") == "bio medical eng"
    assert verify._norm_name(None) == ""

def test_norm_issn():
    assert verify._norm_issn("2456-2156") == "2456-2156"
    assert verify._norm_issn("24562156") == "2456-2156"
    assert verify._norm_issn("0006-821x") == "0006-821X"
    assert verify._norm_issn("not-an-issn") is None
    assert verify._norm_issn(None) is None

def test_load_watchlists_fixture(tmp_path):
    p = tmp_path / "wl.json"
    p.write_text(_json.dumps({
        "meta": {"snapshot_date": "2026-06-05", "sources": {}},
        "predatory_journals": [{"name": "Fake Journal", "issn": ["1111-1111"]}],
        "predatory_publishers": [{"name": "Bad Publisher"}],
        "hijacked_journals": [{"name": "Cloned J", "issn": ["2222-2222"]}],
    }), encoding="utf-8")
    wl = verify.load_watchlists(str(p))
    assert wl["issn"]["1111-1111"] == "predatory"
    assert wl["issn"]["2222-2222"] == "hijacked"
    assert wl["name"]["fake journal"] == "predatory"
    assert wl["publisher"]["bad publisher"] == "predatory"
    assert wl["meta"]["snapshot_date"] == "2026-06-05"

def test_load_watchlists_missing_file():
    wl = verify.load_watchlists("/no/such/watchlists.json")
    assert wl["issn"] == {} and wl["name"] == {} and wl["publisher"] == {}
    assert "note" in wl["meta"]

def test_resolve_refs_doi_path(monkeypatch):
    out = verify.resolve_refs(
        ["Real. Title. 10.1038/s41586-021-03819-2.", "Fake. 10.9999/nope.doi.x 2099."],
        candidate_fetcher=lambda r: [],
        doi_checker=lambda d: d.startswith("10.1038"))
    assert out["provided_unresolved"] == ["Fake. 10.9999/nope.doi.x 2099."]


# ---------------------------------------------------------------------------
# Task 3 (C1 quality): pure helpers
# ---------------------------------------------------------------------------

def test_extract_doi():
    assert verify.extract_doi("Foo. Bar. 2020. https://doi.org/10.1145/3292500.3330701") == "10.1145/3292500.3330701"
    assert verify.extract_doi("A paper, doi:10.1038/s41586-021-03819-2.") == "10.1038/s41586-021-03819-2"
    assert verify.extract_doi("No doi here, just text 2019") is None

def test_ref_year():
    assert verify._ref_year("Smith et al. Title. 2021.") == "2021"
    assert verify._ref_year("no year") is None

def test_match_any_rank3():
    ref = "Vaswani et al. Attention Is All You Need. 2017."
    cands = [{"title": "Wrong One", "year": "2019"},
             {"title": "Another Wrong", "year": "2018"},
             {"title": "Attention Is All You Need", "year": "2017"}]
    assert verify.match_any(ref, cands) is True

def test_match_any_strict_partial_title_no_match():
    # partial title (missing a token) must NOT match under strict rules, even if year matches
    ref = "Doe. Deep Nets. 2020."
    cands = [{"title": "Deep Nets Revisited", "year": "2020"}]  # 'revisited' absent from ref
    assert verify.match_any(ref, cands) is False

def test_match_any_short_title_all_but_one():
    ref = "X. BERT pretraining. 2019."
    cands = [{"title": "BERT", "year": "2019"}]   # 1-token title present
    assert verify.match_any(ref, cands) is True

def test_match_any_all_wrong_no_match():
    ref = "Totally unique fabricated title about quokkas 2099"
    cands = [{"title": "Something unrelated", "year": "2001"}]
    assert verify.match_any(ref, cands) is False

def test_parse_candidates():
    data = {"message": {"items": [
        {"title": ["A Real Title"], "issued": {"date-parts": [[2017]]}},
        {"title": ["Second"], "issued": {"date-parts": [[None]]}}]}}
    out = verify._parse_candidates(data)
    assert out[0] == {"title": "A Real Title", "year": "2017"}
    assert out[1]["title"] == "Second" and out[1]["year"] is None


# ---------------------------------------------------------------------------
# Task 2 (C5): match_venue
# ---------------------------------------------------------------------------

def _wl():
    return {
        "issn": {"2456-2156": "predatory", "0006-8241": "hijacked"},
        "name": {"international journal of innovative science and research technology": "predatory",
                 "bothalia": "hijacked"},
        "publisher": {"omics publishing group": "predatory"},
        "meta": {"snapshot_date": "2026-06-05",
                 "sources": {"predatory_journals": "https://beallslist.net/standalone-journals/"}},
        "entries": {},
    }

def test_match_venue_predatory_by_issn():
    v = {"name": "Whatever", "issn": ["2456-2156"], "publisher": "X"}
    hit = verify.match_venue(v, _wl())
    assert hit["category"] == "predatory" and hit["matched_by"] == "issn"

def test_match_venue_predatory_by_name_when_no_issn():
    v = {"name": "International Journal of Innovative Science and Research Technology",
         "issn": [], "publisher": "X"}
    hit = verify.match_venue(v, _wl())
    assert hit["category"] == "predatory" and hit["matched_by"] == "name"

def test_match_venue_predatory_by_publisher():
    v = {"name": "Some Journal of Stuff", "issn": ["9999-9999"], "publisher": "OMICS Publishing Group"}
    hit = verify.match_venue(v, _wl())
    assert hit["category"] == "predatory" and hit["matched_by"] == "publisher"

def test_match_venue_hijacked_by_issn():
    v = {"name": "Bothalia", "issn": ["0006-8241"], "publisher": "X"}
    hit = verify.match_venue(v, _wl())
    assert hit["category"] == "hijacked" and hit["matched_by"] == "issn"

def test_match_venue_hijacked_outranks_predatory():
    wl = _wl()
    wl["name"]["bothalia"] = "predatory"
    v = {"name": "Bothalia", "issn": ["0006-8241"], "publisher": "X"}
    hit = verify.match_venue(v, wl)
    assert hit["category"] == "hijacked"

def test_match_venue_legit_subscription_no_match():
    for v in ({"name": "BMJ", "issn": ["0959-8138", "1756-1833"], "publisher": "BMJ"},
              {"name": "The Review of Economic Studies", "issn": ["0034-6527"], "publisher": "Oxford University Press"}):
        assert verify.match_venue(v, _wl()) is None

def test_match_venue_empty():
    assert verify.match_venue({}, _wl()) is None
    assert verify.match_venue(None, _wl()) is None


# ---------------------------------------------------------------------------
# Task 3 (C5): compute_flags venue_predatory / venue_hijacked
# ---------------------------------------------------------------------------

def test_flags_venue_predatory():
    f = _facts()
    f["venue"]["watchlist"] = {"category": "predatory", "list": "predatory_journals"}
    fl = verify.compute_flags(f)
    assert fl["venue_predatory"] is True
    assert fl["venue_hijacked"] is False

def test_flags_venue_hijacked():
    f = _facts()
    f["venue"]["watchlist"] = {"category": "hijacked", "list": "hijacked_journals"}
    fl = verify.compute_flags(f)
    assert fl["venue_hijacked"] is True
    assert fl["venue_predatory"] is False

def test_flags_venue_clean_no_watchlist():
    fl = verify.compute_flags(_facts())
    assert fl["venue_hijacked"] is False and fl["venue_predatory"] is False
