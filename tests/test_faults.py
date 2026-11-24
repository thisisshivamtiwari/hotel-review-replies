import json

from review_replies import checks, faults, pipeline

HOTELS, REVIEWS = checks.load()
LANTERN = HOTELS["lantern"]
FOUND = next(r for r in REVIEWS if r["id"] == "lantern-3")


def test_failed_lookup_is_unknown_not_not_found():
    for review in ({**FOUND, "stay_found": None}, {k: v for k, v in FOUND.items() if k != "stay_found"}):
        assert "not known" in pipeline.booking_line(review)
    assert "no stay matching" in pipeline.booking_line({**FOUND, "stay_found": False})


def test_not_found_claim_needs_the_booking_system_to_say_so():
    reply = faults.recorded("lantern-8")
    rules = lambda review: {p["rule"] for p in checks.check_reply(reply, LANTERN, review)}  # noqa: E731
    assert "stay-claim" in rules(FOUND)
    assert "stay-claim" in rules({**FOUND, "stay_found": None})
    assert "stay-claim" not in rules({**FOUND, "stay_found": False})


def test_missing_fact_sheet_fields_are_named():
    assert pipeline.missing_inputs(LANTERN) == []
    gaps = pipeline.missing_inputs({**LANTERN, "contact": " ", "open_issues": None})
    assert gaps == ["fact sheet has no contact", "fact sheet has no open_issues list"]
    assert pipeline.missing_inputs({**LANTERN, "changes": []}) == []  # empty is known: nothing changed


def test_every_fixture_case_is_handled_and_results_reproduce():
    res = faults.run()
    assert res["passed"] == res["cases"]
    assert res == json.loads(faults.OUT.read_text())
