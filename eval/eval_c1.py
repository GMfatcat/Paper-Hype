import os, sys, json, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skill", "paper-verify"))
import verify
sys.path.insert(0, os.path.dirname(__file__)); import metrics

HERE = os.path.dirname(__file__)

def predict(ref, resolve_result):
    return "fake" if ref in (resolve_result.get("provided_unresolved") or []) else "real"

def load(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]

def run(dataset_path, sample_per_label=100):
    rows = load(dataset_path)
    by = {"real": [r for r in rows if r["label"] == "real"],
          "fake": [r for r in rows if r["label"] == "fake"]}
    random.seed(0)
    sample = (random.sample(by["real"], min(sample_per_label, len(by["real"])))
              + random.sample(by["fake"], min(sample_per_label, len(by["fake"]))))
    refs = [r["ref"] for r in sample]
    rr = verify.resolve_refs(refs)              # one batch call to the real resolver
    preds = [predict(r["ref"], rr) for r in sample]
    labels = [r["label"] for r in sample]
    return metrics.precision_recall_fp(preds, labels, positive="fake")

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "datasets", "c1_references.jsonl")
    print(json.dumps({"dataset": os.path.basename(path), **run(path)}, ensure_ascii=False, indent=2))
