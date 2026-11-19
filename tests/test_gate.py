from review_replies import experiment, gate, judge


def row(model, arm, **kw):
    base = {"model": model, "arm": arm, "leaked": 0, "invented": 0, "clean": 10, "compensation": 0, "no_contact": 0}
    return {**base, **kw, "shipped_dirty": kw.get("shipped_dirty", 0)}


def test_gate_compares_against_baseline():
    summary = {
        "table": [
            row("m", "oneshot", leaked=3),
            row("m", "minimised", leaked=1),
            row("m", "checked", leaked=4, clean=9),
        ]
    }
    rules = [
        {"arm": "checked", "metric": "leaked", "max_vs": "oneshot"},
        {"arm": "checked", "metric": "clean", "min_vs": "minimised"},
    ]
    assert gate.evaluate(summary, rules) == ["m checked: leaked = 4 > oneshot (3)", "m checked: clean = 9 < minimised (10)"]


def test_absolute_limit():
    summary = {"table": [row("m", "checked", shipped_dirty=1)]}
    assert gate.evaluate(summary, [{"model": "m", "arm": "checked", "metric": "shipped_dirty", "max": 0}])


def test_wilson_interval():
    assert experiment.wilson(0, 0) == [0.0, 0.0]
    lo, hi = experiment.wilson(16, 32)
    assert 0.33 < lo < 0.35 and 0.65 < hi < 0.67


def test_judge_labels_are_a_fixed_shuffle():
    keys = ["a|oneshot", "a|minimised", "b|oneshot"]
    first = judge.labels_for("lantern-1", keys)
    assert first == judge.labels_for("lantern-1", keys)
    assert sorted(first.values()) == ["A", "B", "C"]


def test_overruled_flags_are_dropped():
    r = {"model": "m", "review": "x", "arm": "oneshot", "judge_issues": [{"type": "leak", "text": "dog"}], "term_leaks": ["dog"]}
    audit = {
        experiment.audit_key(r, "leak", "dog"): "overrule: general fact",
        experiment.audit_key(r, "term", "dog"): "overrule: same",
    }
    assert experiment.kept_issues(r, audit) == []
    assert len(experiment.kept_issues(r, {})) == 2
