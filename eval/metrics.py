def confusion(preds, labels, positive):
    tp = fp = tn = fn = 0
    for p, y in zip(preds, labels):
        if p == positive and y == positive: tp += 1
        elif p == positive and y != positive: fp += 1
        elif p != positive and y != positive: tn += 1
        else: fn += 1
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn}

def precision_recall_fp(preds, labels, positive):
    c = confusion(preds, labels, positive)
    tp, fp, tn, fn = c["tp"], c["fp"], c["tn"], c["fn"]
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    fp_rate = fp / (fp + tn) if (fp + tn) else 0.0
    return {"n": len(labels), "precision": round(precision, 4),
            "recall": round(recall, 4), "false_positive_rate": round(fp_rate, 4), **c}
