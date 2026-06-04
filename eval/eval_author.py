import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skill", "paper-verify"))
import verify
sys.path.insert(0, os.path.dirname(__file__)); import metrics
HERE = os.path.dirname(__file__)

def predict(result):
    return "suspicious" if (result.get("flags") or {}).get("author_identity_weak") else "legit"

def run(path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    preds, labels = [], []
    for r in rows:
        res = verify.verify(r["doi"])
        preds.append(predict(res)); labels.append(r["label"])
    m = metrics.precision_recall_fp(preds, labels, positive="suspicious")
    # primary number is FP rate on legit; also report how many legit total
    m["legit_n"] = sum(1 for l in labels if l == "legit")
    return m

if __name__ == "__main__":
    path = os.path.join(HERE, "datasets", "author_papers.jsonl")
    print(json.dumps({"dataset": "author_papers.jsonl", **run(path)}, ensure_ascii=False, indent=2))
