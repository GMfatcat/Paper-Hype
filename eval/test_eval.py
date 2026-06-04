import eval_c1, eval_c4, eval_author

def test_c1_predict_from_unresolved():
    # resolve_refs returns provided_unresolved; a ref in that list => predicted "fake"
    assert eval_c1.predict("Ref A", {"provided_unresolved": ["Ref A"]}) == "fake"
    assert eval_c1.predict("Ref B", {"provided_unresolved": ["Ref A"]}) == "real"

def test_c4_predict_from_flag():
    assert eval_c4.predict({"flags": {"retracted": True}}) == "retracted"
    assert eval_c4.predict({"flags": {"retracted": False}}) == "clean"

def test_author_predict_from_flag():
    assert eval_author.predict({"flags": {"author_identity_weak": True}}) == "suspicious"
    assert eval_author.predict({"flags": {"author_identity_weak": False}}) == "legit"
