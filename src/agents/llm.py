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
        """{"content": text, "parsed": JSON object or None, "cached": bool, "cost_usd": what this call charges the
        meter (0 if cached), "recorded_cost_usd": the cost of the live call that produced the answer (S33-15 (3)),
        "key": request key}."""
        request = self.request(role, messages)
        key = request_key(request)
        entry = self.cache.get(key)
        if entry is not None:
            self.cached_calls += 1
            return {"content": entry["response"], "parsed": parse_json(entry["response"]), "cached": True,
                    "cost_usd": 0.0, "recorded_cost_usd": float(entry.get("cost_usd", 0.0)), "key": key}
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
        return {"content": content, "parsed": parse_json(content), "cached": False, "cost_usd": cost,
                "recorded_cost_usd": cost, "key": key}


def _usage_dict(usage) -> dict:
    """The integer token counts of an API usage object (nested details dropped)."""
    if usage is None:
        return {}
    raw = usage.model_dump() if hasattr(usage, "model_dump") else dict(usage)
    return {name: int(value) for name, value in raw.items() if isinstance(value, int) and not isinstance(value, bool)}


# -- round 2: the native Messages API of the round-2 lab model (Amendment 9 C2; decisions S43-1, S43-2) ---------------------
#
# The round-1 client above is unchanged, so round 1 replays byte for byte from its cache. Round 2 sends its requests to
# the native Messages endpoint through `requests` (no response_format, no thinking field: thinking is always on for this
# model and its depth is set by output_config.effort; no temperature). The API key is read only from the environment
# variable ROUND2_API_KEY_ENV (round2.agent_lab.api_key_env), only when a live call is made, and is sent only as a request
# header: it is never part of a request dict, a cache line, a log or an error message.
#
# Budget meter (S43-1): a live call costs input_tokens x USD 10 / 1M + output_tokens x USD 50 / 1M (output includes the
# thinking tokens) + cache writes (5-minute USD 12.50, 1-hour USD 20 / 1M) + cache reads (USD 0.25 / 1M), from the usage the
# API returns. Before each live call, the cost of every call in every round-2 cache file (ROUND2_CACHE_GLOBS) plus a
# worst-case bound of the new call (prompt characters as tokens at the highest input rate, plus max_tokens at the output
# rate) must not exceed the round-2 hard stop (round2.agent_lab.budget_usd, USD 10), else BudgetExceeded is raised and no
# call is made. Round 1's USD 5 meter is separate.

ROUND2_MODEL = "claude-fable-5-1"  # S43-1: listed by GET /v1/models on 6 Nov 2026
ROUND2_URL = "https://api.anthropic.com/v1/messages"
ROUND2_API_VERSION = "2023-06-01"
ROUND2_API_KEY_ENV = "DDMI_ANTHROPIC_API_KEY"  # round2.agent_lab.api_key_env (S40-1); never ANTHROPIC_API_KEY
ROUND2_USD_PER_MTOK = {"input": 10.0, "output": 50.0, "cache_write_5m": 12.50, "cache_write_1h": 20.0, "cache_read": 0.25}
ROUND2_EFFORT = "medium"  # S43-1: chosen after the 3 calibration calls (Eliya, 6 Nov 2026)
ROUND2_MAX_TOKENS = 6000  # S43-1: 2.8 times the largest output measured (2,155 tokens, thinking included)
ROUND2_MEASURED_OUTPUT_TOKENS = 2052  # S43-1: output tokens of the medium-effort calibration call (probe projection)
RESERVE_FIXED_CHARS = 8000  # S43-1: bound of the fixed prompt text of a Coder, repair, Skeptic or Risk call
RESERVE_INSERTED_ANSWERS = {"coder": 1, "repair": 2, "skeptic": 2, "risk": 1}  # LLM answers each call quotes
ROUND2_CACHE_TTL = "1h"  # S43-2: prompt caching of the stable prefix of the Hypothesis prompt
ROUND2_TIMEOUT = (30, 900)  # seconds: connect, read (a long thinking turn is not cut off)
ROUND2_RETRIES = 2  # connection errors, timeouts, HTTP 429, 5xx and 529 only; any other error raises at once
ROUND2_RETRY_WAIT = (10.0, 30.0)  # seconds before the first and the second retry
ROUND2_CACHE_GLOBS = ("agent_lab/cache/planted_round2*.jsonl", "agent_lab/run2/cache/*.jsonl")  # every round-2 cache file
_RETRY_STATUS = (429, 500, 502, 503, 504, 529)


class Round2APIError(RuntimeError):
    """The round-2 API returned an error that is not retried, or every retry failed. The message holds the HTTP status
    and the API's error type and message, never a header or the key."""


def round2_call_cost(usage: dict) -> float:
    """USD cost of a round-2 live call from its flattened usage (S43-1). Cache writes without a TTL breakdown are priced
    at the 1-hour rate (the higher one)."""
    price = {name: value / 1_000_000 for name, value in ROUND2_USD_PER_MTOK.items()}
    write_5m = int(usage.get("cache_creation_ephemeral_5m_input_tokens", 0))
    write_1h = int(usage.get("cache_creation_ephemeral_1h_input_tokens", 0))
    unsplit = max(int(usage.get("cache_creation_input_tokens", 0)) - write_5m - write_1h, 0)
    return (int(usage.get("input_tokens", 0)) * price["input"] + int(usage.get("output_tokens", 0)) * price["output"]
            + write_5m * price["cache_write_5m"] + (write_1h + unsplit) * price["cache_write_1h"]
            + int(usage.get("cache_read_input_tokens", 0)) * price["cache_read"])


def _text_of(content) -> str:
    """The text of a message content: a string, or the concatenated text of a list of text blocks."""
    if isinstance(content, str):
        return content
    return "".join(str(block.get("text", "")) for block in content if isinstance(block, dict))


def round2_worst_case_cost(request: dict) -> float:
    """Upper bound of a round-2 call's cost before it is made: every prompt character counted as a token at the highest
    input rate (the 1-hour cache write), plus max_tokens output tokens (thinking included) at the output rate."""
    characters = len(request.get("system", "")) + sum(len(_text_of(m["content"])) for m in request["messages"])
    highest_input = max(ROUND2_USD_PER_MTOK["input"], ROUND2_USD_PER_MTOK["cache_write_1h"]) / 1_000_000
    return characters * highest_input + int(request["max_tokens"]) * ROUND2_USD_PER_MTOK["output"] / 1_000_000


def round2_candidate_worst_case(hypothesis_request: dict, *, max_tokens: int = ROUND2_MAX_TOKENS,
                                coder_repairs: int = 1) -> float:
    """Worst-case cost of one more candidate before it starts (S43-1, the probe reserve): the Hypothesis request's worst
    case (round2_worst_case_cost) plus, for each later call the candidate may make (the Coder, `coder_repairs` repairs,
    the Skeptic, Risk), RESERVE_FIXED_CHARS characters and max_tokens tokens per quoted LLM answer at the highest input
    rate, plus max_tokens output tokens. A quoted answer has at most max_tokens tokens because it was generated within
    max_tokens."""
    highest_input = max(ROUND2_USD_PER_MTOK["input"], ROUND2_USD_PER_MTOK["cache_write_1h"]) / 1_000_000
    output = ROUND2_USD_PER_MTOK["output"] / 1_000_000
    calls = ["coder"] + ["repair"] * int(coder_repairs) + ["skeptic", "risk"]
    later = sum((RESERVE_FIXED_CHARS + RESERVE_INSERTED_ANSWERS[c] * int(max_tokens)) * highest_input
                + int(max_tokens) * output for c in calls)
    return round2_worst_case_cost(hypothesis_request) + later


def round2_probe_projection(probe_requests: Sequence[dict]) -> float:
    """Projected cost of the recognition probe (S43-1): per request, its prompt characters at the input rate plus the
    output tokens measured on the medium-effort calibration call at the output rate."""
    return float(sum((len(request.get("system", "")) + sum(len(_text_of(m["content"])) for m in request["messages"]))
                     * ROUND2_USD_PER_MTOK["input"] / 1_000_000
                     + ROUND2_MEASURED_OUTPUT_TOKENS * ROUND2_USD_PER_MTOK["output"] / 1_000_000
                     for request in probe_requests))


def round2_request(role: str, messages: Sequence[dict], *, max_tokens: int = ROUND2_MAX_TOKENS,
                   effort: str = ROUND2_EFFORT) -> dict:
    """The request of a round-2 call: the role (lab metadata, not sent), the system text (the prompts' system messages
    joined), the user and assistant turns as given (a content may be a list of text blocks with cache_control), max_tokens
    and output_config.effort. No response_format, thinking, temperature or credential field (S43-2)."""
    system = "\n\n".join(_text_of(m["content"]) for m in messages if m["role"] == "system")
    turns = [{"role": m["role"], "content": m["content"] if isinstance(m["content"], str) else [dict(b) for b in m["content"]]}
             for m in messages if m["role"] != "system"]
    return {"model": ROUND2_MODEL, "role": role, "system": system, "messages": turns, "max_tokens": int(max_tokens),
            "output_config": {"effort": str(effort)}}


def round2_body(request: dict) -> dict:
    """The JSON body sent to the Messages endpoint: the request without the lab's `role` field."""
    return {key: value for key, value in request.items() if key != "role"}


def round2_usage(usage: dict | None) -> dict:
    """The integer token counts of a Messages API usage object, with the cache-write TTL breakdown flattened."""
    out = {name: int(value) for name, value in (usage or {}).items()
           if isinstance(value, int) and not isinstance(value, bool)}
    for ttl, value in ((usage or {}).get("cache_creation") or {}).items():
        if isinstance(value, int) and not isinstance(value, bool):
            out[f"cache_creation_{ttl}"] = int(value)
    return out


def parse_json_round2(text: str) -> dict | None:
    """parse_json (S33-13) after removing one Markdown code fence around the whole answer, if there is one (S43-2)."""
    if isinstance(text, str):
        stripped = text.strip()
        if stripped.startswith("```") and stripped.endswith("```") and stripped.count("```") == 2:
            inner = stripped[3:-3]
            text = inner.split("\n", 1)[1] if "\n" in inner else ""
    return parse_json(text)


def round2_spend(root: Path = ROOT) -> float:
    """USD cost of every live call in every round-2 cache file (ROUND2_CACHE_GLOBS under root), each key once."""
    seen: dict[str, float] = {}
    for pattern in ROUND2_CACHE_GLOBS:
        for path in sorted(Path(root).glob(pattern)):
            with open(path, encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        entry = json.loads(line)
                        seen.setdefault(entry["key"], float(entry.get("cost_usd", 0.0)))
    return float(sum(seen.values()))


def _messages_transport(api_key_env: str = ROUND2_API_KEY_ENV) -> Callable[[dict], dict]:
    """A function body -> response JSON over HTTPS, with the key from `api_key_env` in the x-api-key header only."""
    import time

    import requests

    key = os.environ.get(api_key_env)
    if not key:
        raise RuntimeError(f"{api_key_env} is not set: a live round-2 lab run needs it (replay mode does not)")
    if key != key.strip():  # requests would quote an invalid header value, key included, in its error message
        raise RuntimeError(f"{api_key_env} has leading or trailing whitespace; set it again without it")
    session = requests.Session()
    session.headers.update({"x-api-key": key, "anthropic-version": ROUND2_API_VERSION, "content-type": "application/json"})

    def send(body: dict) -> dict:
        last = "no attempt"
        for attempt in range(ROUND2_RETRIES + 1):
            if attempt:
                time.sleep(ROUND2_RETRY_WAIT[min(attempt, len(ROUND2_RETRY_WAIT)) - 1])
            try:
                response = session.post(ROUND2_URL, json=body, timeout=ROUND2_TIMEOUT)
            except (requests.ConnectionError, requests.Timeout) as error:
                last = type(error).__name__
                continue
            except requests.RequestException as error:  # never retried; its message may quote a header, so it is dropped
                raise Round2APIError(f"round-2 Messages API call failed: {type(error).__name__}") from None
            if response.status_code == 200:
                return response.json()
            try:
                error = response.json().get("error", {})
                detail = f"{error.get('type')}: {error.get('message')}"
            except ValueError:
                detail = response.text[:300]
            last = f"HTTP {response.status_code} {detail}"
            if response.status_code not in _RETRY_STATUS:
                break
        raise Round2APIError(f"round-2 Messages API call failed: {last}")

    return send


@dataclass
class Round2LLM:
    """The round-2 lab model (S43-1, S43-2): answers from the cache, or (live mode) from the native Messages API within
    the round-2 hard stop. Same interface as LLM: call(role, messages) -> {"content", "parsed", "cached", "cost_usd",
    "recorded_cost_usd", "key"}, plus "stop_reason" and "usage".

    cache: LLMCache of the run's folder; spend: USD already spent by round 2 (default round2_spend, every round-2 cache
    file); transport_factory: api_key_env -> (body -> response JSON) (tests pass a fake). Counters as LLM.
    """

    cache: LLMCache
    mode: str = "replay"
    budget_usd: float = 10.0
    max_tokens: int = ROUND2_MAX_TOKENS
    effort: str = ROUND2_EFFORT
    api_key_env: str = ROUND2_API_KEY_ENV
    spend: Callable[[], float] = round2_spend
    transport_factory: Callable[[str], Callable[[dict], dict]] = _messages_transport
    live_calls: int = 0
    cached_calls: int = 0
    run_cost: float = 0.0
    _transport: object = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"LLM mode must be one of {MODES}, got {self.mode!r}")

    def request(self, role: str, messages: Sequence[dict]) -> dict:
        return round2_request(role, messages, max_tokens=self.max_tokens, effort=self.effort)

    def call(self, role: str, messages: Sequence[dict]) -> dict:
        request = self.request(role, messages)
        key = request_key(request)
        entry = self.cache.get(key)
        if entry is not None:
            self.cached_calls += 1
            return {"content": entry["response"], "parsed": parse_json_round2(entry["response"]), "cached": True,
                    "cost_usd": 0.0, "recorded_cost_usd": float(entry.get("cost_usd", 0.0)), "key": key,
                    "stop_reason": entry.get("stop_reason"), "usage": entry.get("usage", {})}
        if self.mode == "replay":
            raise ReplayMiss(f"replay: no cached response for the {role} request {key[:12]}")
        spent = float(self.spend())
        if spent + round2_worst_case_cost(request) > self.budget_usd:
            raise BudgetExceeded(f"the next {role} call could take the round-2 spend above USD {self.budget_usd} "
                                 f"(spent {spent:.4f}); no call made (S43-1)")
        if self._transport is None:
            self._transport = self.transport_factory(self.api_key_env)
        response = self._transport(round2_body(request))
        content = "".join(str(block.get("text", "")) for block in response.get("content", [])
                          if isinstance(block, dict) and block.get("type") == "text")
        usage = round2_usage(response.get("usage"))
        cost = round2_call_cost(usage)
        stop_reason = response.get("stop_reason")
        self.cache.add({"key": key, "request": request, "response": content, "usage": usage, "cost_usd": cost,
                        "stop_reason": stop_reason, "served_model": response.get("model")})
        self.live_calls += 1
        self.run_cost += cost
        return {"content": content, "parsed": parse_json_round2(content), "cached": False, "cost_usd": cost,
                "recorded_cost_usd": cost, "key": key, "stop_reason": stop_reason, "usage": usage}
