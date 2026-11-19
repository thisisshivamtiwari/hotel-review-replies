"""The independent judge: Claude Sonnet 5.5 at its default effort, with its own prompt. It is the only model that sees
the private notes next to the replies. One call per review scores all eight replies (4 arms x 2 models) under shuffled
letters, so it can't tell which setup or model wrote which. It never feeds back into a pipeline; each of its flags was
then reviewed one by one (audit/labels.yaml).
"""

import random

from . import llm, pipeline

JUDGE = "sonnet-5.5"
TYPES = ("leak", "invented", "compensation", "accusation", "generic-action")
SEVERE = ("leak", "invented", "compensation", "accusation")


def labels_for(review_id: str, keys: list[str]) -> dict[str, str]:
    """A fixed shuffle per review: {key: letter}."""
    order = list(keys)
    random.Random(review_id).shuffle(order)
    return {k: chr(ord("A") + i) for i, k in enumerate(order)}


def judge(hotel: dict, review: dict, replies: dict[str, str]) -> dict:
    """replies: {key: text}. Returns {"issues": {key: [issue]}, "unparsed", "cost_usd", "ms"}."""
    letters = labels_for(review["id"], sorted(replies))
    blocks = "\n\n".join(f"REPLY {letters[k]}\n{replies[k]}" for k in sorted(replies, key=letters.get))
    user = (
        f"FACT SHEET\n{pipeline.fact_sheet(hotel)}\n{pipeline.review_block(review)}\n\n"
        f"{pipeline.private_block(review)}\n\n{blocks}"
    )
    res = llm.call(JUDGE, pipeline.prompt("judge"), user, purpose="judge", effort=None)
    found = llm.parse_json(res["text"])
    items = found.get("replies") if isinstance(found, dict) else None
    out: dict[str, list] = {k: [] for k in replies}
    if not isinstance(items, list):
        return {"issues": out, "unparsed": True, "cost_usd": res["cost_usd"], "ms": res["ms"]}
    by_letter = {v: k for k, v in letters.items()}
    for item in items:
        key = by_letter.get(str(item.get("label", "")).strip()) if isinstance(item, dict) else None
        if key is None:
            continue
        out[key] = [
            {"type": i["type"], "text": str(i.get("text", "")), "why": str(i.get("why", ""))}
            for i in item.get("issues") or []
            if isinstance(i, dict) and i.get("type") in TYPES
        ]
    return {"issues": out, "unparsed": False, "cost_usd": res["cost_usd"], "ms": res["ms"]}
