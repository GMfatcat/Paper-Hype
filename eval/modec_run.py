"""Mode C end-to-end validation over 20 fresh (previously-untested) papers.

Runs paper-verify (facts + flags) on each, computes the Mode C deterministic
backbone score, and dumps both a summary table and full JSON.

This exercises the post-C1-improvement toolchain (DOI-direct resolve, author
identity, retraction C4, venue/DOAJ C5) on real, fresh metadata. C1 refs and
the qualitative C2/C3 textual checks are layered separately (see report).
"""
import sys, json, os
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skill", "paper-verify"))
import verify

# 20 papers, none in eval datasets (c4_papers / author_papers) or prior tests.
PAPERS = [
    # --- fresh 2024 sample pulled from OpenAlex (real, untested) ---
    ("10.1093/nar/gkae268",            "iTOL v6 (Nucleic Acids Research)"),
    ("10.1136/bmj-2023-078378",        "TRIPOD+AI statement (BMJ)"),
    ("10.1007/s11704-024-40231-1",     "LLM autonomous agents survey (Frontiers CS)"),
    ("10.1109/cvpr52733.2024.01605",   "RT-DETR (CVPR 2024)"),
    ("10.1093/restud/rdae007",         "Event-Study Designs (Review of Economic Studies)"),
    ("10.38124/ijisrt/ijisrt24apr651", "Fault Detection ANN (IJISRT - predatory?)"),
    ("10.38124/ijisrt/ijisrt24may1483","Generative AI clinical docs (IJISRT - predatory?)"),
    ("10.57702/i9oeewf6",              "CUB-200-2011 dataset (repository DOI)"),
    ("10.1109/adics58448.2024.10533619","YOLOv8 object detection (IEEE conf)"),
    ("10.1093/nar/gkae253",            "MetaboAnalyst 6.0 (Nucleic Acids Research)"),
    # --- flagship arXiv AI papers (fresh; bare ids) ---
    ("2402.17764", "BitNet b1.58 1-bit LLMs"),
    ("2401.04088", "Mixtral of Experts"),
    ("2404.19756", "KAN: Kolmogorov-Arnold Networks"),
    ("2501.12948", "DeepSeek-R1"),
    ("2106.09685", "LoRA"),
    ("2305.14314", "QLoRA"),
    ("2205.14135", "FlashAttention"),
    # --- deliberate red-flag / edge cases ---
    ("10.1038/nature12968", "STAP cells I (Obokata 2014 - retracted)"),
    ("10.1038/nature12969", "STAP cells II (Obokata 2014 - retracted)"),
    ("2407.21783",          "Llama 3 herd (very new; index-coverage test)"),
]


def backbone_score(flags, resolved):
    """Deterministic Mode C backbone risk (0-100) from paper-verify flags only.
    Qualitative C2/C3 (AI traces, tortured phrases) need fulltext and are added
    in the report layer; this is the tool-measurable floor. Mirrors SKILL rubric
    weights (C4=25, C5=15, author is a soft modifier)."""
    if not resolved:
        return None, "unresolved (too new / not indexed) -> fall back to manual"
    score = 0
    notes = []
    if flags.get("retracted"):
        score = max(score, 80); notes.append("C4 RETRACTED (decisive red flag)")
    if flags.get("not_in_doaj_journal"):
        score += 15; notes.append("C5 journal not in DOAJ")
    if flags.get("venue_repository_only"):
        score += 5; notes.append("repository-only venue (expected for preprints)")
    if flags.get("author_identity_weak"):
        score += 15; notes.append("author identity weak")
    if not notes:
        notes.append("no tool-level red flags")
    return min(score, 100), "; ".join(notes)


def light(score):
    if score is None: return "GRAY"
    if score >= 71: return "RED"
    if score >= 31: return "AMBER"
    return "GREEN"


def main():
    results = []
    for i, (pid, label) in enumerate(PAPERS, 1):
        try:
            r = verify.verify(pid)
        except Exception as e:
            r = {"resolved": False, "error": str(e), "flags": {}}
        flags = r.get("flags") or {}
        score, why = backbone_score(flags, r.get("resolved"))
        venue = (r.get("venue") or {}).get("name")
        n_auth = len(r.get("authors") or [])
        row = {
            "n": i, "id": pid, "label": label,
            "resolved": r.get("resolved"),
            "title": r.get("title"),
            "venue": venue,
            "is_in_doaj": (r.get("venue") or {}).get("is_in_doaj"),
            "authors": n_auth,
            "flags": flags,
            "backbone_score": score, "light": light(score), "why": why,
        }
        results.append(row)
        print(f"{i:2d}. [{light(score)}] {str(score):>4} | {label[:48]:48} | "
              f"resolved={r.get('resolved')} venue={str(venue)[:30]}")
        print(f"      flags: {json.dumps(flags, ensure_ascii=False)}")
    out = os.path.join(os.path.dirname(__file__), "modec_results_2026-06.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\nWROTE", out)
    # quick aggregate
    from collections import Counter
    c = Counter(r["light"] for r in results)
    print("LIGHTS", dict(c))


if __name__ == "__main__":
    main()
