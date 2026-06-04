import metrics

def test_confusion_basic():
    preds  = ["fake","fake","real","real"]
    labels = ["fake","real","real","fake"]
    c = metrics.confusion(preds, labels, positive="fake")
    assert c == {"tp": 1, "fp": 1, "tn": 1, "fn": 1}

def test_prf_all_correct():
    m = metrics.precision_recall_fp(["fake","real"], ["fake","real"], positive="fake")
    assert m["precision"] == 1.0 and m["recall"] == 1.0 and m["false_positive_rate"] == 0.0

def test_prf_all_wrong():
    m = metrics.precision_recall_fp(["real","fake"], ["fake","real"], positive="fake")
    assert m["recall"] == 0.0 and m["false_positive_rate"] == 1.0

def test_prf_handles_zero_denominator():
    # no positives predicted, no positives present -> precision/recall defined as 1.0, fp 0.0
    m = metrics.precision_recall_fp(["real","real"], ["real","real"], positive="fake")
    assert m["false_positive_rate"] == 0.0
    assert m["n"] == 2

def test_prf_fp_rate_definition():
    # fp_rate = fp / (fp+tn): 1 real wrongly called fake out of 2 reals -> 0.5
    m = metrics.precision_recall_fp(["fake","real","real"], ["real","real","fake"], positive="fake")
    assert m["false_positive_rate"] == 0.5
