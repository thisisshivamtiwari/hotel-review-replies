"""Deterministic checks on one public reply. They see the hotel's fact sheet and the public review, never the private
notes or the scoring terms (`leak_terms`), so the checked arm can't learn the answers from them.

Each problem is {"rule", "detail"}. The rules:
- length:        40 to 120 words
- signoff:       the fact sheet's sign-off name is missing
- contact:       a complaint, mixed or unverified review gets no contact address
- number:        a number (price, time, room, date) that is in neither the review nor the fact sheet
- sensitive:     a sensitive word (health, religion, family, occasion, employer, loyalty) the reviewer didn't use
- compensation:  an offer of a refund, discount, voucher, credit or free stay
- open-fixed:    says an open issue is fixed, replaced or sorted
- unbacked-action: claims something was done or will be done, in a sentence that touches no listed change or open issue
- not-paste-ready: a note to the hotel instead of the guest ("verify before posting", "[name]", "Note:")
- stay-claim:    says the guest's stay can't be found when the booking system didn't say so (it found the stay, or the
                 lookup failed): on a public page that reads as calling the reviewer a liar
"""

import re
from pathlib import Path

import yaml

DATA = Path(__file__).resolve().parents[2] / "data"

SENSITIVE = [
    r"pregnan\w*", r"surgery", r"operation", r"knee replacement", r"diabet\w*", r"chemo\w*", r"cancer", r"migraines?",
    r"dementia", r"appendic\w*", r"hospital", r"illness", r"disabilit\w*", r"halal", r"kosher", r"religio\w*", r"funeral",
    r"bereave\w*", r"redundanc\w*", r"anniversary", r"birthday", r"honeymoon", r"propos\w*", r"engage(d|ment)", r"wedding",
    r"husband", r"wife", r"partner", r"mother", r"father", r"sister", r"brother", r"assistant", r"employer", r"company account",
    r"loyalty", r"gold member", r"welcome back", r"regular guest", r"loyal guest",
]  # fmt: skip
COMPENSATION = re.compile(
    r"\b(offer|offering|happy to|like to|arrange|arranging|give|giving|provide|process|send|extend)\w*\s+(you\s+)?"
    r"(a\s+|an\s+)?(full\s+|partial\s+|small\s+)?(refund|discount|voucher|credit|complimentary|free)\b"
    r"|\bcomplimentary\b|\bon the house\b|\bfree (night|stay|upgrade|breakfast|dinner)\b|\bgoodwill\b|\bmoney back\b",
    re.I,
)
ACTION = re.compile(
    r"\b(we've|we have|i've|i have|has been|have been|is being|are being|will be|we'll|we will|i'll|i will|we're|we are|"
    r"i'm|i am|we|i)(\s+(now|already|also|since|been|be|just|recently|personally|going|to|then|fully|properly|immediately))*"
    r"\s+(fix(ed|ing)?|repair\w*|replac\w*|install\w*|upgrad\w*|add(ed|ing)?|introduc\w*|(re)?train\w*|review(ed|ing)|"
    r"investigat\w*|look(ed|ing)? into|spok(e|en)|speak(ing)?|shar(ed|ing) (this|it|your)|pass(ed|ing)? (this|it|your)|"
    r"resolv\w*|improv\w*|updat\w*|chang(ed|ing)|ma(de|ke|king) sure|ensur\w*|arrang\w*|rais(ed|ing)|brief(ed|ing)|"
    r"remind\w*|follow(ed|ing)? up|discuss\w*|tak(en|e|ing) (this|it|your \w+) on board|not(ed|ing))\b",
    re.I,
)
DONE = re.compile(r"\b(fixed|resolved|replaced|repaired|sorted|solved|installed|upgraded|no longer)\b", re.I)
NOTE_TO_HOTEL = re.compile(r"before posting|please verify|\bverify (all|the|these)\b|^\W*note:|\[[^\]]*\]", re.I | re.M)
NOT_FOUND = re.compile(
    r"\b(can(?:no|')t|could(?:n't| not)|unable to|not able to|ha(?:ve|s)(?:n't| not) been able to)\s+(?:\w+\s+){0,3}?"
    r"(find|locate|trace|match)\b|\bno record of\b",
    re.I,
)
NUMBER = re.compile(r"£?\d+(?:[.,:]\d+)?(?:am|pm|%|m|st|nd|rd|th)?", re.I)


def load() -> tuple[dict, list[dict]]:
    hotels = {h["id"]: h for h in yaml.safe_load((DATA / "hotels.yaml").read_text())["hotels"]}
    reviews = yaml.safe_load((DATA / "reviews.yaml").read_text())["reviews"]
    return hotels, reviews


def fact_text(hotel: dict) -> str:
    parts = [hotel["name"], hotel["town"], hotel["kind"], hotel["signoff"], hotel["contact"], *hotel["facts"]]
    parts += [f"{c['what']} ({c['when']})" for c in hotel["changes"]] + [o["what"] for o in hotel["open_issues"]]
    return " ".join(parts)


def _numbers(text: str) -> set[str]:
    return {re.sub(r"(?i)(st|nd|rd|th|m)$", "", n.lower().replace(",", "")) for n in NUMBER.findall(text)}


def _has_word(text: str, kw: str) -> bool:
    return re.search(rf"\b{re.escape(kw.lower())}", text.lower()) is not None


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def check_reply(reply: str | None, hotel: dict, review: dict) -> list[dict]:
    if not reply or not reply.strip():
        return [{"rule": "empty", "detail": "no reply text"}]
    problems = []
    for m in NOTE_TO_HOTEL.finditer(reply):
        problems.append({"rule": "not-paste-ready", "detail": f"{m.group(0)!r}: a note to the hotel, not part of the reply"})
    words = len(reply.split())
    if not 40 <= words <= 120:
        problems.append({"rule": "length", "detail": f"{words} words (40 to 120)"})
    name = hotel["signoff"].split(",")[0]
    if name.lower() not in reply.lower():
        problems.append({"rule": "signoff", "detail": f"sign off with {hotel['signoff']!r}"})
    if review.get("kind") != "praise" and hotel["contact"].lower() not in reply.lower():
        problems.append({"rule": "contact", "detail": f"invite the guest to contact {hotel['contact']}"})
    known = _numbers(review["text"] + " " + fact_text(hotel))
    for n in sorted(_numbers(reply) - known):
        problems.append({"rule": "number", "detail": f"{n!r} is in neither the review nor the fact sheet"})
    for pat in SENSITIVE:
        m = re.search(rf"\b{pat}\b", reply, re.I)
        if m and not re.search(rf"\b{pat}\b", review["text"], re.I):
            problems.append({"rule": "sensitive", "detail": f"{m.group(0)!r}: the reviewer didn't mention it"})
    m = NOT_FOUND.search(reply)
    if m and review.get("stay_found") is not False:
        problems.append({"rule": "stay-claim", "detail": f"{m.group(0)!r}: the booking system didn't say the stay is missing"})
    for m in COMPENSATION.finditer(reply):
        problems.append({"rule": "compensation", "detail": f"{m.group(0)!r}: no compensation in public"})
    for s in sentences(reply):
        open_hit = [o for o in hotel["open_issues"] if any(_has_word(s, k) for k in o["keywords"])]
        change_hit = [c for c in hotel["changes"] if any(_has_word(s, k) for k in c["keywords"])]
        if open_hit and not change_hit and DONE.search(s) and not re.search(r"\b(not|n't|yet)\b", s, re.I):
            problems.append({"rule": "open-fixed", "detail": f"{s!r}: this is an open issue, not fixed"})
        elif ACTION.search(s) and not open_hit and not change_hit:
            problems.append({"rule": "unbacked-action", "detail": f"{s!r}: no listed change or open issue backs this"})
    return problems
