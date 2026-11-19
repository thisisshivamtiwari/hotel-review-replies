from review_replies import checks, experiment

HOTELS, REVIEWS = checks.load()
REV = {r["id"]: r for r in REVIEWS}
SIGN = "Please email stay@lanternrooms.example and I will call you back. Tom Hale, General Manager"
PAD = "Thank you for taking the time to write about your stay with us at The Lantern Rooms in Pellingford this autumn."


def rules(reply: str, rid: str = "lantern-2") -> list[str]:
    review = REV[rid]
    return [p["rule"] for p in checks.check_reply(reply, HOTELS[review["hotel"]], review)]


def test_clean_reply_passes():
    reply = (
        f"{PAD} I'm sorry the shower ran lukewarm. The cause isn't known yet; a plumber visit is booked for 2 December. {SIGN}"
    )
    assert rules(reply) == []


def test_open_issue_claimed_fixed():
    assert "open-fixed" in rules(f"{PAD} The hot water has now been fixed in every room. {SIGN}")


def test_open_issue_not_yet_fixed_is_fine():
    assert "open-fixed" not in rules(f"{PAD} The hot water is not fixed yet, and I won't pretend otherwise. {SIGN}")


def test_listed_change_backs_an_action():
    reply = f"{PAD} We have updated the kiosk software so card payments no longer fail. {SIGN}"
    assert "unbacked-action" not in rules(reply, "lantern-4")


def test_unlisted_action_is_flagged():
    assert "unbacked-action" in rules(f"{PAD} I have passed this on to our housekeeping team. {SIGN}")


def test_room_number_is_an_unknown_number():
    assert "number" in rules(f"{PAD} Room 31 has a slow shower. {SIGN}")


def test_numbers_from_the_review_and_fact_sheet_are_allowed():
    assert "number" not in rules(f"{PAD} Ten minutes of lukewarm water is not right; reception is staffed 7am to 11pm. {SIGN}")


def test_sensitive_word_only_when_reviewer_did_not_use_it():
    assert "sensitive" in rules(f"{PAD} We hope you and your partner come back. {SIGN}")
    assert "sensitive" not in rules(f"{PAD} I'm sorry about your bad knee and the stairs. {SIGN}", "saltmarsh-3")


def test_public_compensation():
    assert "compensation" in rules(f"{PAD} We would like to offer you a full refund. {SIGN}")
    assert "compensation" not in rules(f"{PAD} Park-and-fly rates are non-refundable. {SIGN}")


def test_contact_needed_for_complaints_not_praise():
    no_contact = f"{PAD} Thank you so much. We hope to see you again. Tom Hale, General Manager"
    assert "contact" in rules(no_contact)
    assert "contact" not in rules(no_contact, "lantern-1")


def test_note_to_hotel_is_not_paste_ready():
    assert "not-paste-ready" in rules(f"{PAD} {SIGN}\n\n*Please verify all details before posting.*")


def test_length_and_empty():
    assert "length" in rules(f"Thanks. {SIGN}")
    assert rules("") == ["empty"]


def test_term_leaks_skip_terms_the_reviewer_wrote():
    review = REV["saltmarsh-3"]
    assert experiment.term_leaks("Sorry about the knee replacement and room 7.", review) == ["replacement", "room 7"]
    assert experiment.term_leaks("Sorry about the stairs.", review) == []


def test_every_review_has_a_hotel_and_known_kind():
    assert len(REVIEWS) == 32
    for r in REVIEWS:
        assert r["hotel"] in HOTELS and r["kind"] in {"praise", "complaint", "mixed", "suspect"}
        assert r["stay_found"] == (r["kind"] != "suspect")
