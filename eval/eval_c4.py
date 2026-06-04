import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skill", "paper-verify"))
import verify
sys.path.insert(0, os.path.dirname(__file__)); import metrics
HERE = os.path.dirname(__file__)

def predict(result):
    return "retracted" if (result.get("flags") or {}).get("retracted") else "clean"

def run(path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    preds, labels = [], []
    for r in rows:
        res = verify.verify(r["doi"])
        preds.append(predict(res)); labels.append(r["label"])
    return metrics.precision_recall_fp(preds, labels, positive="retracted")

if __name__ == "__main__":
    path = os.path.join(HERE, "datasets", "c4_papers.jsonl")
    print(json.dumps({"dataset": "c4_papers.jsonl", **run(path)}, ensure_ascii=False, indent=2))
