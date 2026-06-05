"""C5 venue calibration: does the watchlist flag predatory/hijacked venues
without false-positiving reputable journals? positive class = "flagged"
(venue_predatory OR venue_hijacked). Reports precision / recall / FP via metrics.py.

Note: a hijacked-journal positive (a paper in the cloned *Bothalia*) has no stable
DOI in this set; hijacked detection is covered by unit test
test_match_venue_hijacked_by_issn. Add a hijacked DOI here if a stable one is found.
"""
import sys, os, json
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "skill", "paper-verify"))
import verify
import metrics

def predict(result):
    fl = result.get("flags") or {}
    return "flagged" if (fl.get("venue_predatory") or fl.get("venue_hijacked")) else "clean"

def run(path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    preds, labels = [], []
    for r in rows:
        res = verify.verify(r["id"])
        pred = predict(res)
        label = "flagged" if r["expect"] == "flagged" else "clean"
        preds.append(pred); labels.append(label)
        print(f'{r["venue"]:30} expect={r["expect"]:7} got={pred:7} resolved={res.get("resolved")}')
    m = metrics.precision_recall_fp(preds, labels, positive="flagged")
    print(json.dumps(m, ensure_ascii=False, indent=2))
    return m

if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "datasets", "c5_venues.jsonl")
    run(p)
