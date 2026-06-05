"""C1 end-to-end validation on a fresh arXiv subset.

For each paper: extract references via pdf-extract (arXiv HTML / regex fallback),
then run the improved resolve_refs (DOI-direct + top-1 title match) and report
how many of the REAL references resolve. On real papers nearly all refs should
resolve; a high unresolved ratio on a real paper would indicate the C1 path is
over-flagging (the FP concern). This is a live check of the shipped C1 path.
"""
import sys, os, json
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "skill", "paper-verify"))
sys.path.insert(0, os.path.join(HERE, "..", "skill", "pdf-extract"))
import verify
import extract

SUBSET = [
    ("2402.17764", "BitNet b1.58"),
    ("2404.19756", "KAN"),
    ("2106.09685", "LoRA"),
]


def main():
    rows = []
    for pid, label in SUBSET:
        try:
            ext = extract.extract(pid)
        except Exception as e:
            ext = {"ok": False, "error": str(e), "references": [], "references_source": "none"}
        refs = ext.get("references") or []
        src = ext.get("references_source") or ext.get("source")
        # cap refs to keep Crossref calls bounded for a live check
        sample = refs[:40]
        rr = verify.resolve_refs(sample) if sample else {"provided_checked": 0, "provided_unresolved": []}
        n = rr["provided_checked"]
        un = len(rr["provided_unresolved"])
        ratio = round(un / n, 3) if n else None
        row = {
            "id": pid, "label": label,
            "references_count": len(refs), "references_source": src,
            "checked": n, "unresolved": un, "unresolved_ratio": ratio,
            "sample_unresolved": rr["provided_unresolved"][:5],
        }
        rows.append(row)
        print(f"{label:12} | refs={len(refs):3} src={src:14} | checked={n:2} "
              f"unresolved={un:2} ratio={ratio}")
        for u in rr["provided_unresolved"][:3]:
            print("        UNRESOLVED:", (u or "")[:90])
    out = os.path.join(HERE, "modec_c1_results_2026-06.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print("\nWROTE", out)


if __name__ == "__main__":
    main()
