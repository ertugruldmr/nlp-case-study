from ftlink.confidence import RelationCalibrator, fit_platt
from ftlink.linking import LinkDecision


def _decision(ce, rules, lex, accepted):
    return LinkDecision(
        summary_row_id="s", footnote_row_id="f", period_scope="y2012",
        relation_type="semantic",
        approach_scores={"cross_encoder": ce, "value_rules": rules, "lexical": lex},
        approach_accepts={"cross_encoder": accepted, "value_rules": accepted,
                          "lexical": False},
        agreement="consensus" if accepted else "none",
    )


def _fitted_calibrator():
    pos = [_decision(0.9, 1.0, 0.4, True) for _ in range(4)]
    neg = [_decision(0.05, 0.0, 0.1, False) for _ in range(5)]
    calib = RelationCalibrator()
    calib.fit_with_checks(pos + neg, ["pass"] * 4 + ["not_evaluable"] * 5)
    return calib


def test_platt_survives_perfect_separation():
    # separated controls diverge in plain logistic regression; Platt target
    # smoothing must keep the fit finite and usable
    calib = _fitted_calibrator()
    assert calib.mode == "fitted"
    assert calib.n_pos == 4 and calib.n_neg == 5


def test_reconciliation_boost_never_saturates():
    calib = _fitted_calibrator()
    d = _decision(0.95, 1.0, 0.5, True)
    boosted = calib.confidence(d, "pass")
    assert boosted.value < 1.0
    assert calib.confidence(d, "fail").value < calib.confidence(d, "not_evaluable").value < boosted.value


def test_venn_abers_interval_brackets():
    calib = _fitted_calibrator()
    va = calib.venn_abers(0.7)
    assert va is not None
    p0, p1 = va
    assert 0.0 <= p0 <= p1 <= 1.0


def test_loo_stability_reports_bounded_movement():
    pos = [_decision(0.85 + i * 0.02, 1.0, 0.4, True) for i in range(4)]
    neg = [_decision(0.02 + i * 0.02, 0.0, 0.1, False) for i in range(5)]
    calib = RelationCalibrator()
    calib.fit_with_checks(pos + neg, ["pass"] * 4 + ["not_evaluable"] * 5)
    loo = calib.loo_stability()
    assert loo is not None
    assert 0.0 <= loo["loo_max_delta_p"] <= 1.0


def test_degenerate_control_set_falls_back():
    calib = RelationCalibrator()
    calib.fit_with_checks([_decision(0.9, 1.0, 0.4, True)], ["pass"])
    assert calib.mode == "fallback"
    assert calib.venn_abers(0.5) is None
    assert fit_platt([(0.9, 1), (0.1, 0)]) is None


def test_consensus_without_reconciliation_is_not_a_positive():
    # regression guard for the mock-03 waiver: EVERY positive needs the
    # reconciliation signature, consensus included
    pos_candidate = _decision(0.9, 1.0, 0.4, True)  # agreement=consensus
    neg = [_decision(0.05, 0.0, 0.1, False) for _ in range(5)]
    calib = RelationCalibrator()
    calib.fit_with_checks([pos_candidate] + neg, ["fail"] + ["not_evaluable"] * 5)
    assert calib.n_pos == 0


def test_llm_only_acceptance_enters_no_control_pool():
    d = _decision(0.1, 0.0, 0.1, False)
    d.approach_accepts["llm_select"] = True
    calib = RelationCalibrator()
    calib.fit_with_checks([d], ["fail"])
    assert calib.n_pos == 0 and calib.n_neg == 0


def test_separation_is_disclosed():
    pos = [_decision(0.9, 1.0, 0.4, True) for _ in range(4)]
    neg = [_decision(0.05, 0.0, 0.1, False) for _ in range(5)]
    calib = RelationCalibrator()
    calib.fit_with_checks(pos + neg, ["pass"] * 4 + ["not_evaluable"] * 5)
    assert calib.separated is True
    overlap = _decision(0.95, 1.0, 0.5, False)  # a negative above the positives
    calib2 = RelationCalibrator()
    calib2.fit_with_checks(pos + neg + [overlap],
                           ["pass"] * 4 + ["not_evaluable"] * 6)
    assert calib2.separated is False
