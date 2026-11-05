"""LLM calls of the research lab (protocol section 08; decisions S33-1 and S33-7): the OpenAI-compatible client of the
pre-registered model, the hashed JSONL cache that replays the lab offline at zero cost, and the USD hard stop.

Every call is one line of agent_lab/cache/<run>.jsonl: key = SHA-256 of the canonical JSON of the request (model,
messages, parameters), the request, the response text, the API's usage and the cost in USD. No time, machine field or
credential is written. A request whose key is in any cache file is answered from it at zero cost; in replay mode a
missing key raises ReplayMiss and no client or API key is needed. The API key is read from the environment variable
DEEPSEEK_API_KEY only when a live call is made, and is never logged, cached or returned.

Budget meter (S33-1): a live call costs prompt_tokens × USD 0.30 / 1M + completion_tokens × USD 1.20 / 1M (the peak
cache-miss input and peak output prices of the pricing page read on 3 Nov 2026). Before each live call, the cost of
every call in every cache file plus a worst-case bound of the new call (prompt characters counted as tokens, plus
max_tokens output tokens) must not exceed the budget, else BudgetExceeded is raised and no call is made.
"""

import hashlib
import json
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from src.config import ROOT

MODEL = "deepseek-flash"  # §08: DeepSeek V4.1 Flash; listed by the /models endpoint on 3 Nov 2026 (S33-1)
BASE_URL = "https://api.deepseek.com"
API_KEY_ENV = "DEEPSEEK_API_KEY"
INPUT_USD_PER_TOKEN = 0.30 / 1_000_000  # peak, cache miss (S33-1)
OUTPUT_USD_PER_TOKEN = 1.20 / 1_000_000  # peak (S33-1)
MAX_TOKENS = 1500
CACHE_DIR = ROOT / "agent_lab" / "cache"
MODES = ("live", "replay")


class BudgetExceeded(RuntimeError):
    """The next live call could take the total spend above the hard budget (S33-1); no call was made."""


class ReplayMiss(RuntimeError):
    """Replay mode met a request that is not in the cache."""


def canonical(value) -> str:
    """Canonical JSON: sorted keys, no spaces, UTF-8 text kept as is."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def request_key(request: dict) -> str:
    """SHA-256 (hex) of the canonical JSON of a request."""
    return hashlib.sha256(canonical(request).encode("utf-8")).hexdigest()


def call_cost(usage: dict) -> float:
    """USD cost of a live call from its usage (S33-1): every prompt token at the peak cache-miss price."""
    return int(usage.get("prompt_tokens", 0)) * INPUT_USD_PER_TOKEN + int(usage.get("completion_tokens", 0)) * OUTPUT_USD_PER_TOKEN


def worst_case_cost(request: dict) -> float:
    """Upper bound of a call's cost before it is made: prompt characters as tokens plus max_tokens output tokens."""
    characters = sum(len(str(message.get("content", ""))) for message in request["messages"])
    return characters * INPUT_USD_PER_TOKEN + int(request["max_tokens"]) * OUTPUT_USD_PER_TOKEN


def parse_json(text: str) -> dict | None:
    """The JSON object of a response, or None when it is blank or not a JSON object. A complete object followed only by
    surplus closing brackets or whitespace (a miscounted deep nesting) is accepted as that object (S33-13)."""
    if not isinstance(text, str):
        return None
    try:
        value = json.loads(text)
    except ValueError:
        start = text.find("{")
        if start < 0:
            return None
        try:
            value, end = json.JSONDecoder().raw_decode(text, start)
        except ValueError:
            return None
        if text[:start].strip() or text[end:].strip().strip("}]").strip():
            return None
    return value if isinstance(value, dict) else None


class LLMCache:
    """Every cache file *.jsonl of `directory`, read at start; new entries are appended to <directory>/<run>.jsonl."""

    def __init__(self, directory: Path = CACHE_DIR, run: str = "lab") -> None:
        self.directory = Path(directory)
        self.path = self.directory / f"{run}.jsonl"
        self.entries: dict[str, dict] = {}
        if self.directory.is_dir():
            for path in sorted(self.directory.glob("*.jsonl")):
                with open(path, encoding="utf-8") as handle:
                    for line in handle:
                        if line.strip():
                            entry = json.loads(line)
                            self.entries.setdefault(entry["key"], entry)

    def total_cost(self) -> float:
        """USD cost of every live call recorded in the cache files (each key once)."""
        return float(sum(float(entry.get("cost_usd", 0.0)) for entry in self.entries.values()))

    def get(self, key: str) -> dict | None:
        return self.entries.get(key)

    def add(self, entry: dict) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical(entry) + "\n")
        self.entries[entry["key"]] = entry


def _openai_client():
    from openai import OpenAI

    key = os.environ.get(API_KEY_ENV)
    if not key:
        raise RuntimeError(f"{API_KEY_ENV} is not set: a live lab run needs it (replay mode does not)")
    return OpenAI(api_key=key, base_url=BASE_URL)


@dataclass
class LLM:
    """The lab's language model: answers from the cache, or (live mode) from the API within the budget.

    mode: "live" or "replay"; budget_usd: agent_lab.budget_usd; client_factory: returns an OpenAI-compatible client
    (tests pass a fake). Counters: live_calls, cached_calls, run_cost (USD of this object's live calls).
    """

    cache: LLMCache
    mode: str = "replay"
    budget_usd: float = 5.0
    max_tokens: int = MAX_TOKENS
    client_factory: Callable[[], object] = _openai_client
    live_calls: int = 0
    cached_calls: int = 0
    run_cost: float = 0.0
    _client: object = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"LLM mode must be one of {MODES}, got {self.mode!r}")

    def request(self, role: str, messages: Sequence[dict]) -> dict:
        """The request of a call: model, role, messages and the fixed parameters of S33-1."""
        return {"model": MODEL, "role": role, "messages": [dict(m) for m in messages], "max_tokens": int(self.max_tokens),
                "response_format": {"type": "json_object"}, "thinking": {"type": "disabled"}}

    def call(self, role: str, messages: Sequence[dict]) -> dict:
        """{"content": text, "parsed": JSON object or None, "cached": bool, "cost_usd": cost of this call (0 if
        cached), "key": request key}."""
        request = self.request(role, messages)
        key = request_key(request)
        entry = self.cache.get(key)
        if entry is not None:
            self.cached_calls += 1
            return {"content": entry["response"], "parsed": parse_json(entry["response"]), "cached": True,
                    "cost_usd": 0.0, "key": key}
        if self.mode == "replay":
            raise ReplayMiss(f"replay: no cached response for the {role} request {key[:12]}")
        if self.cache.total_cost() + worst_case_cost(request) > self.budget_usd:
            raise BudgetExceeded(f"the next {role} call could take the spend above USD {self.budget_usd} "
                                 f"(spent {self.cache.total_cost():.4f}); no call made (S33-1)")
        if self._client is None:
            self._client = self.client_factory()
        response = self._client.chat.completions.create(
            model=request["model"], messages=request["messages"], max_tokens=request["max_tokens"],
            response_format=request["response_format"], extra_body={"thinking": request["thinking"]})
        content = response.choices[0].message.content or ""
        usage = _usage_dict(response.usage)
        cost = call_cost(usage)
        self.cache.add({"key": key, "request": request, "response": content, "usage": usage, "cost_usd": cost})
        self.live_calls += 1
        self.run_cost += cost
        return {"content": content, "parsed": parse_json(content), "cached": False, "cost_usd": cost, "key": key}


def _usage_dict(usage) -> dict:
    """The integer token counts of an API usage object (nested details dropped)."""
    if usage is None:
        return {}
    raw = usage.model_dump() if hasattr(usage, "model_dump") else dict(usage)
    return {name: int(value) for name, value in raw.items() if isinstance(value, int) and not isinstance(value, bool)}
