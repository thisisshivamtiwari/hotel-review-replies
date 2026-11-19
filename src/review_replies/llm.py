"""Model calls through the Claude Code CLI (`claude -p`), recorded to cassettes so CI can replay them.

A cassette entry is keyed by a hash of (model, system prompt, user prompt, sample number). `HRR_MODE=record` calls
the model for any key not yet on disk; the default, `replay`, never calls a model and fails on a missing key. Each
entry keeps the CLI's own cost (`total_cost_usd`, at API list prices) and duration, which is where the cost and
latency figures in results/ come from.
"""

import hashlib
import json
import os
import re
import subprocess
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASSETTES = ROOT / "cassettes"
MODELS = {"haiku-4.5": "claude-haiku-4-5-20251001", "sonnet-5.5": "claude-sonnet-5-5"}
_lock = threading.Lock()
_cache: dict[str, dict[str, dict]] = {}


class MissingCassette(KeyError):
    pass


def _key(model: str, system: str, prompt: str, sample: int, effort: str | None) -> str:
    raw = json.dumps([model, system, prompt, sample] + ([effort] if effort else []), ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _load(alias: str) -> dict[str, dict]:
    if alias not in _cache:
        path = CASSETTES / f"{alias}.jsonl"
        lines = path.read_text().splitlines() if path.exists() else []
        _cache[alias] = {e["key"]: e for e in map(json.loads, lines)}
    return _cache[alias]


# Haiku 4.5 doesn't support the effort setting, and the CLI ignores --effort for it without a warning
# (anthropics/claude-code#96386), so pipeline calls only pass it to Sonnet.
EFFORT = {"haiku-4.5": None, "sonnet-5.5": "low"}


def call(alias: str, system: str, prompt: str, sample: int = 0, purpose: str = "", effort: str | None = "pipeline") -> dict:
    """Return {text, cost_usd, ms, cached} for one model call. Pipeline calls use EFFORT; effort=None leaves the CLI
    default (the judge)."""
    if effort == "pipeline":
        effort = EFFORT[alias]
    key = _key(MODELS[alias], system, prompt, sample, effort)
    with _lock:
        hit = _load(alias).get(key)
    if hit:
        return {**hit, "cached": True}
    if os.environ.get("HRR_MODE", "replay") != "record":
        raise MissingCassette(f"{alias} {purpose} sample {sample}: no recording for key {key}; run with HRR_MODE=record")
    out = subprocess.run(
        ["claude", "-p", prompt, "--model", MODELS[alias], "--output-format", "json", "--tools", "",
         "--strict-mcp-config", "--setting-sources", "", "--system-prompt", system]
        + (["--effort", effort] if effort else []),
        capture_output=True, text=True, check=True, timeout=600, stdin=subprocess.DEVNULL, cwd="/tmp",
    )  # fmt: skip
    res = json.loads(out.stdout)
    entry = {
        "key": key,
        "purpose": purpose,
        "sample": sample,
        "effort": effort,
        "text": res["result"],
        "cost_usd": res["total_cost_usd"],
        "ms": res["duration_ms"],
        "input_tokens": res["usage"]["input_tokens"],
        "output_tokens": res["usage"]["output_tokens"],
    }
    with _lock:
        CASSETTES.mkdir(exist_ok=True)
        with (CASSETTES / f"{alias}.jsonl").open("a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        _load(alias)[key] = entry
    return {**entry, "cached": False}


def parse_json(text: str):
    """The first JSON object or array in a reply (models sometimes wrap it in a code fence). None if there isn't one."""
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    body = fenced.group(1) if fenced else text
    start = min((i for i in (body.find("{"), body.find("[")) if i >= 0), default=-1)
    if start < 0:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(body[start:])
        return obj
    except json.JSONDecodeError:
        return None
