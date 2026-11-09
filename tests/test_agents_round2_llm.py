"""The round-2 lab client of src/agents/llm.py and the round-2 prompts (decisions S43-1, S43-2, S43-5; Amendment 9 C2).

Written from the decisions and the session's interface only. Every live call goes through a fake transport, or through
the real transport with requests patched: no network, no real key (sentinel strings only), no spend. Round 1's client,
request, cache keys and committed cache sums are checked unchanged.
"""

import hashlib
import json
import re

import pytest
import requests

from src.agents import llm, prompts
from src.config import ROOT, load_config

DDMI_SENTINEL = "ddmi-test-SENTINEL-key-7f3a9c"
OTHER_SENTINEL = "other-env-SENTINEL-key-0b1d2e"
VENDOR = re.compile(r"anthropic|claude", re.IGNORECASE)
ORIGIN = re.compile(r"planted|injected|noise", re.IGNORECASE)
MESSAGES = [{"role": "system", "content": "Answer in json."}, {"role": "user", "content": "Propose a feature."}]
ANSWER = '{"mechanism": "m", "rationale": "r", "feature_idea": "f"}'
USAGE = {"input_tokens": 1200, "output_tokens": 800, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
CACHE_LINE_KEYS = {"key", "request", "response", "usage", "cost_usd", "stop_reason", "served_model"}
REQUEST_KEYS = {"model", "role", "system", "messages", "max_tokens", "output_config"}


def response_json(text=ANSWER, usage=None, stop_reason="end_turn", thinking="internal reasoning text"):
    return {"content": [{"type": "thinking", "thinking": thinking}, {"type": "text", "text": text}],
            "usage": dict(USAGE if usage is None else usage), "stop_reason": stop_reason, "model": "claude-fable-5-1"}


class FakeTransport:
    """transport_factory(api_key_env) -> transport(body) -> response JSON; records every factory call and body."""

    def __init__(self, response=None):
        self.response = response_json() if response is None else response
        self.factory_calls, self.bodies = [], []

    def factory(self, *args, **kwargs):
        self.factory_calls.append((args, kwargs))
        return self.transport

    def transport(self, body):
        self.bodies.append(json.loads(json.dumps(body)))
        return json.loads(json.dumps(self.response))


def make(tmp_path, *, mode="live", run="planted_round2", transport=None, spend=0.0, budget=10.0):
    transport = transport or FakeTransport()
    model = llm.Round2LLM(llm.LLMCache(tmp_path, run), mode=mode, budget_usd=budget, spend=lambda: spend,
                          transport_factory=transport.factory)
    return model, transport


def cache_lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def text_of(messages) -> str:
    """Every text of a message list, whether a content is a string or a list of text blocks."""
    parts = []
    for message in messages:
        content = message.get("content", "")
        if isinstance(content, str):
            parts.append(content)
        else:
            parts.extend(str(block.get("text", "")) for block in content)
    return "\n".join(parts)


# ---------------------------------------------------------------- S43-1: constants


def test_round2_constants():
    assert llm.ROUND2_MODEL == "claude-fable-5-1"
    assert llm.ROUND2_API_KEY_ENV == "DDMI_ANTHROPIC_API_KEY"
    assert llm.ROUND2_API_KEY_ENV == load_config()["round2"]["agent_lab"]["api_key_env"]
    assert llm.ROUND2_USD_PER_MTOK == {"input": 10.0, "output": 50.0, "cache_write_5m": 12.50, "cache_write_1h": 20.0,
                                       "cache_read": 0.25}
    assert llm.ROUND2_CACHE_GLOBS == ("agent_lab/cache/planted_round2*.jsonl", "agent_lab/run2/cache/*.jsonl")


def test_effort_and_max_tokens_are_recorded_values():
    """S43-1: effort is one of the model's levels (low ... xhigh, max); max_tokens a positive int within the model's
    128000 output limit."""
    assert isinstance(llm.ROUND2_EFFORT, str) and llm.ROUND2_EFFORT in ("low", "medium", "high", "xhigh", "max")
    assert isinstance(llm.ROUND2_MAX_TOKENS, int) and not isinstance(llm.ROUND2_MAX_TOKENS, bool)
    assert 0 < llm.ROUND2_MAX_TOKENS <= 128000


def test_the_hard_stop_is_usd_10():
    assert float(load_config()["round2"]["agent_lab"]["budget_usd"]) == 10.0
    model = llm.Round2LLM(llm.LLMCache(ROOT / "agent_lab" / "this_folder_is_never_created"), mode="replay")
    assert model.budget_usd == 10.0


# ---------------------------------------------------------------- S43-1: the meter


@pytest.mark.parametrize("usage, expected", [
    ({"input_tokens": 1_000_000}, 10.0),
    ({"output_tokens": 1_000_000}, 50.0),
    ({"cache_read_input_tokens": 1_000_000}, 0.25),
    ({"cache_creation_input_tokens": 1_000_000, "cache_creation_ephemeral_5m_input_tokens": 1_000_000}, 12.5),
    ({"cache_creation_input_tokens": 1_000_000, "cache_creation_ephemeral_1h_input_tokens": 1_000_000}, 20.0),
    ({"cache_creation_input_tokens": 1_000_000}, 20.0),  # no TTL breakdown: the 1-hour rate
    ({"cache_creation_input_tokens": 300, "cache_creation_ephemeral_5m_input_tokens": 100,
      "cache_creation_ephemeral_1h_input_tokens": 200}, (100 * 12.5 + 200 * 20.0) / 1e6),
    ({"input_tokens": 1200, "output_tokens": 800, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
     1200 * 10e-6 + 800 * 50e-6),
    ({"input_tokens": 50, "output_tokens": 4000, "cache_creation_input_tokens": 6000,
      "cache_creation_ephemeral_5m_input_tokens": 0, "cache_creation_ephemeral_1h_input_tokens": 6000,
      "cache_read_input_tokens": 9000}, (50 * 10 + 4000 * 50 + 6000 * 20 + 9000 * 0.25) / 1e6),
    ({}, 0.0),
])
def test_call_cost_prices_every_token_class(usage, expected):
    assert llm.round2_call_cost(usage) == pytest.approx(expected, rel=1e-12, abs=1e-15)


def test_thinking_tokens_are_priced_as_output():
    """Thinking is billed inside usage.output_tokens (S43-1): 10000 output tokens cost USD 0.50 whatever they hold."""
    assert llm.round2_call_cost({"input_tokens": 0, "output_tokens": 10_000}) == pytest.approx(0.5, rel=1e-12)


def test_usage_flattens_the_ttl_breakdown_and_keeps_ints_only():
    api = {"input_tokens": 10, "output_tokens": 20, "cache_creation_input_tokens": 30, "cache_read_input_tokens": 40,
           "cache_creation": {"ephemeral_5m_input_tokens": 5, "ephemeral_1h_input_tokens": 25},
           "service_tier": "standard", "server_tool_use": None}
    assert llm.round2_usage(api) == {
        "input_tokens": 10, "output_tokens": 20, "cache_creation_input_tokens": 30, "cache_read_input_tokens": 40,
        "cache_creation_ephemeral_5m_input_tokens": 5, "cache_creation_ephemeral_1h_input_tokens": 25}
    assert all(type(value) is int for value in llm.round2_usage(api).values())


def test_worst_case_counts_system_and_every_message_text_at_usd_20_plus_max_tokens_at_usd_50():
    messages = [{"role": "system", "content": "S" * 100},
                {"role": "user", "content": [{"type": "text", "text": "a" * 300,
                                              "cache_control": {"type": "ephemeral", "ttl": "1h"}},
                                             {"type": "text", "text": "b" * 50}]},
                {"role": "assistant", "content": "c" * 7},
                {"role": "user", "content": "d" * 43}]
    request = llm.round2_request("hypothesis", messages, max_tokens=2000)
    expected = (100 + 300 + 50 + 7 + 43) * 20 / 1e6 + 2000 * 50 / 1e6
    assert llm.round2_worst_case_cost(request) == pytest.approx(expected, rel=1e-12)


def test_round2_spend_sums_the_round2_cache_files_once_per_key(tmp_path):
    def write(relative, entries):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")

    entry = lambda key, cost: {"key": key * 64, "request": {}, "response": "{}", "usage": {}, "cost_usd": cost}
    write("agent_lab/cache/planted_round2.jsonl", [entry("a", 1.0)])
    write("agent_lab/cache/planted_round2_attempt.jsonl", [entry("b", 0.5)])
    write("agent_lab/run2/cache/insample.jsonl", [entry("c", 2.0), entry("a", 1.0)])  # key a counted once
    write("agent_lab/run2/cache/calibration.jsonl", [entry("d", 0.125)])
    write("agent_lab/cache/planted.jsonl", [entry("e", 100.0)])  # round 1: not counted
    write("agent_lab/run/cache/insample.jsonl", [entry("f", 50.0)])  # round 1: not counted
    assert llm.round2_spend(tmp_path) == pytest.approx(3.625, rel=1e-12)


def test_round2_spend_of_an_empty_root_is_zero(tmp_path):
    assert llm.round2_spend(tmp_path) == 0.0


# ---------------------------------------------------------------- S43-2: the request


def test_round2_request_shape():
    messages = [{"role": "system", "content": "First system part."}, {"role": "system", "content": "Second part."},
                {"role": "user", "content": [{"type": "text", "text": "stable",
                                              "cache_control": {"type": "ephemeral", "ttl": "1h"}},
                                             {"type": "text", "text": "variable"}]},
                {"role": "assistant", "content": "an earlier answer"},
                {"role": "user", "content": "again"}]
    request = llm.round2_request("coder", messages, max_tokens=1234, effort="high")
    assert request == {"model": "claude-fable-5-1", "role": "coder", "system": "First system part.\n\nSecond part.",
                       "messages": messages[2:], "max_tokens": 1234, "output_config": {"effort": "high"}}
    assert llm.round2_body(request) == {key: value for key, value in request.items() if key != "role"}
    assert "role" in request  # round2_body does not change its argument


def test_round2_request_defaults_and_forbidden_fields():
    """S43-2 / session §4: no response_format, no thinking field, no temperature or other sampling parameter, no
    credential; max_tokens and effort are the recorded constants."""
    request = llm.round2_request("hypothesis", MESSAGES)
    assert set(request) == REQUEST_KEYS
    assert request["max_tokens"] == llm.ROUND2_MAX_TOKENS
    assert request["output_config"] == {"effort": llm.ROUND2_EFFORT}
    for field in ("response_format", "thinking", "temperature", "top_p", "top_k", "extra_body", "api_key"):
        assert field not in request and field not in llm.round2_body(request)


# ---------------------------------------------------------------- S43-2: the answer parser


@pytest.mark.parametrize("text", [
    '{"spec": {"name": "a"}}',
    '```json\n{"spec": {"name": "a"}}\n```',
    '```\n{"spec": {"name": "a"}}\n```',
    '  ```json\n{"spec": {"name": "a"}}\n```  \n',
])
def test_parse_json_round2_removes_one_enclosing_fence(text):
    assert llm.parse_json_round2(text) == {"spec": {"name": "a"}}


@pytest.mark.parametrize("text", [
    'Here it is: ```json\n{"a": 1}\n```',
    '```json\n{"a": 1}\n``` and more',
    '```json\n```json\n{"a": 1}\n```\n```',
    "```json\n[1, 2]\n```",
    "",
    "   ",
    None,
    '{"a": 1} trailing words',
])
def test_parse_json_round2_relaxes_nothing_else(text):
    assert llm.parse_json_round2(text) is None


def test_parse_json_round2_keeps_the_s33_13_rescue():
    assert llm.parse_json_round2('```json\n{"a": {"b": 1}}}}\n```') == llm.parse_json('{"a": {"b": 1}}}}') == {"a": {"b": 1}}


# ---------------------------------------------------------------- S43-2: Round2LLM with a fake transport


def test_live_call_sends_the_body_and_writes_one_cache_line(tmp_path):
    model, transport = make(tmp_path)
    out = model.call("hypothesis", MESSAGES)
    expected_cost = 1200 * 10e-6 + 800 * 50e-6
    assert set(out) >= {"content", "parsed", "cached", "cost_usd", "recorded_cost_usd", "key", "stop_reason", "usage"}
    assert out["content"] == ANSWER and out["parsed"] == json.loads(ANSWER)
    assert out["cached"] is False
    assert out["cost_usd"] == pytest.approx(expected_cost) and out["recorded_cost_usd"] == pytest.approx(expected_cost)
    assert out["stop_reason"] == "end_turn" and out["usage"] == USAGE
    request = llm.round2_request("hypothesis", MESSAGES)
    assert transport.bodies == [llm.round2_body(request)]
    assert len(transport.factory_calls) == 1
    assert llm.ROUND2_API_KEY_ENV in json.dumps(transport.factory_calls[0], default=str)
    lines = cache_lines(tmp_path / "planted_round2.jsonl")
    assert len(lines) == 1
    entry = lines[0]
    assert set(entry) == CACHE_LINE_KEYS
    assert entry["request"] == request and entry["key"] == llm.request_key(request) == out["key"]
    assert entry["response"] == ANSWER and entry["usage"] == USAGE
    assert entry["cost_usd"] == pytest.approx(expected_cost)
    assert entry["stop_reason"] == "end_turn" and entry["served_model"] == "claude-fable-5-1"
    assert "internal reasoning text" not in (tmp_path / "planted_round2.jsonl").read_text(encoding="utf-8")


def test_the_cache_line_holds_the_flattened_usage(tmp_path):
    usage = {"input_tokens": 100, "output_tokens": 2000, "cache_creation_input_tokens": 4000,
             "cache_read_input_tokens": 0, "cache_creation": {"ephemeral_5m_input_tokens": 0,
                                                              "ephemeral_1h_input_tokens": 4000}}
    model, _ = make(tmp_path, transport=FakeTransport(response_json(usage=usage)))
    out = model.call("hypothesis", MESSAGES)
    entry = cache_lines(tmp_path / "planted_round2.jsonl")[0]
    flat = llm.round2_usage(usage)
    assert entry["usage"] == flat == out["usage"]
    assert entry["cost_usd"] == pytest.approx((100 * 10 + 2000 * 50 + 4000 * 20) / 1e6, rel=1e-12)


def test_a_cached_request_costs_nothing_and_keeps_its_recorded_cost(tmp_path):
    first, _ = make(tmp_path)
    live = first.call("coder", MESSAGES)
    again, transport = make(tmp_path, run="other")
    out = again.call("coder", MESSAGES)
    assert out["cached"] is True and out["cost_usd"] == 0.0
    assert out["recorded_cost_usd"] == pytest.approx(live["cost_usd"])
    assert transport.factory_calls == [] and transport.bodies == []
    assert not (tmp_path / "other.jsonl").exists()


def test_replay_answers_from_the_cache_without_a_transport_and_raises_on_a_miss(tmp_path):
    first, _ = make(tmp_path)
    first.call("skeptic", MESSAGES)

    def no_transport(*args, **kwargs):
        raise AssertionError("replay must not build a transport")

    replay = llm.Round2LLM(llm.LLMCache(tmp_path, "replay"), mode="replay", transport_factory=no_transport,
                           spend=lambda: 0.0)
    assert replay.call("skeptic", MESSAGES)["parsed"] == json.loads(ANSWER)
    with pytest.raises(llm.ReplayMiss):
        replay.call("risk", MESSAGES)


def test_the_budget_refuses_a_call_whose_worst_case_crosses_the_stop(tmp_path):
    probe, _ = make(tmp_path / "probe")
    worst = llm.round2_worst_case_cost(llm.round2_request("hypothesis", MESSAGES, max_tokens=probe.max_tokens,
                                                          effort=probe.effort))
    model, transport = make(tmp_path, spend=10.0 - worst + 1e-6)
    with pytest.raises(llm.BudgetExceeded):
        model.call("hypothesis", MESSAGES)
    assert transport.factory_calls == [] and transport.bodies == []
    assert not (tmp_path / "planted_round2.jsonl").exists()
    allowed, transport2 = make(tmp_path / "ok", spend=10.0 - worst - 1e-6)
    assert allowed.call("hypothesis", MESSAGES)["cached"] is False
    assert len(transport2.bodies) == 1


def test_the_budget_reads_spend_before_every_live_call(tmp_path):
    spent = {"value": 0.0}
    transport = FakeTransport()
    model = llm.Round2LLM(llm.LLMCache(tmp_path, "run"), mode="live", budget_usd=10.0, spend=lambda: spent["value"],
                          transport_factory=transport.factory)
    model.call("hypothesis", MESSAGES)
    spent["value"] = 9.9999
    with pytest.raises(llm.BudgetExceeded):
        model.call("coder", MESSAGES)
    assert len(transport.bodies) == 1


@pytest.mark.parametrize("stop_reason, text", [("refusal", ""), ("max_tokens", '{"spec": {"name": "cut')])
def test_a_refused_or_truncated_answer_is_kept_and_parses_to_none(tmp_path, stop_reason, text):
    model, _ = make(tmp_path, transport=FakeTransport(response_json(text=text, stop_reason=stop_reason)))
    out = model.call("coder", MESSAGES)
    assert out["parsed"] is None and out["content"] == text and out["stop_reason"] == stop_reason
    entry = cache_lines(tmp_path / "planted_round2.jsonl")[0]
    assert entry["stop_reason"] == stop_reason and entry["response"] == text


def test_a_fenced_answer_is_parsed(tmp_path):
    model, _ = make(tmp_path, transport=FakeTransport(response_json(text="```json\n" + ANSWER + "\n```")))
    assert model.call("hypothesis", MESSAGES)["parsed"] == json.loads(ANSWER)


# ---------------------------------------------------------------- S43-2: the real transport (requests patched)


class FakeHTTP:
    def __init__(self, status=200, payload=None):
        self.status_code, self._payload = status, response_json() if payload is None else payload
        self.ok = 200 <= status < 300
        self.text = json.dumps(self._payload)
        self.headers = {"content-type": "application/json"}

    def json(self):
        return json.loads(self.text)

    def raise_for_status(self):
        if not self.ok:
            raise requests.HTTPError(f"{self.status_code}", response=self)


@pytest.fixture
def http(monkeypatch):
    """requests.Session.request patched (Session.post and requests.post both go through it); responses queued."""
    sent, queue = [], []

    def fake_request(self, method, url, *args, **kwargs):
        merged = {**dict(getattr(self, "headers", {}) or {}), **dict(kwargs.get("headers") or {})}  # session + call
        sent.append({"method": method, "url": url, **kwargs, "headers": merged})
        return queue.pop(0) if queue else FakeHTTP()

    monkeypatch.setattr(requests.Session, "request", fake_request)
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    if hasattr(llm, "time"):
        monkeypatch.setattr(llm.time, "sleep", lambda seconds: None, raising=False)
    if hasattr(llm, "sleep"):
        monkeypatch.setattr(llm, "sleep", lambda seconds: None)
    monkeypatch.setenv(llm.ROUND2_API_KEY_ENV, DDMI_SENTINEL)
    monkeypatch.setenv("ANTHROPIC_API_KEY", OTHER_SENTINEL)
    return sent, queue


def test_the_real_transport_needs_the_ddmi_variable(monkeypatch):
    monkeypatch.delenv(llm.ROUND2_API_KEY_ENV, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", OTHER_SENTINEL)
    with pytest.raises(RuntimeError):
        transport = llm._messages_transport(llm.ROUND2_API_KEY_ENV)
        transport(llm.round2_body(llm.round2_request("hypothesis", MESSAGES)))


@pytest.mark.parametrize("padded", [" {}", "{}\r\n", "{}\n", "\t{}"])
def test_a_key_with_surrounding_whitespace_is_refused_without_quoting_it(monkeypatch, padded):
    """requests would quote an invalid header value, key included, in its error (audit finding M1 of session 4.3)."""
    monkeypatch.setenv(llm.ROUND2_API_KEY_ENV, padded.format(DDMI_SENTINEL))
    with pytest.raises(RuntimeError) as caught:
        llm._messages_transport(llm.ROUND2_API_KEY_ENV)
    assert DDMI_SENTINEL not in str(caught.value) and llm.ROUND2_API_KEY_ENV in str(caught.value)


def test_a_request_error_is_raised_without_its_message(monkeypatch):
    import requests

    monkeypatch.setenv(llm.ROUND2_API_KEY_ENV, DDMI_SENTINEL)

    def boom(self, *args, **kwargs):
        raise requests.exceptions.InvalidHeader(f"Invalid leading whitespace in header value: {DDMI_SENTINEL!r}")

    monkeypatch.setattr(requests.Session, "request", boom)
    with pytest.raises(llm.Round2APIError) as caught:
        llm._messages_transport(llm.ROUND2_API_KEY_ENV)(llm.round2_body(llm.round2_request("hypothesis", MESSAGES)))
    assert DDMI_SENTINEL not in str(caught.value) and caught.value.__cause__ is None


def test_the_real_transport_posts_to_messages_with_the_ddmi_key_only(http):
    sent, _ = http
    body = llm.round2_body(llm.round2_request("hypothesis", MESSAGES))
    answer = llm._messages_transport(llm.ROUND2_API_KEY_ENV)(body)
    assert answer["content"][-1]["text"] == ANSWER
    assert len(sent) == 1
    call = sent[0]
    assert call["method"].upper() == "POST" and call["url"].endswith("/v1/messages")
    headers = {k.lower(): v for k, v in (call.get("headers") or {}).items()}
    assert headers["x-api-key"] == DDMI_SENTINEL
    assert headers["anthropic-version"] == "2023-06-01"
    assert OTHER_SENTINEL not in json.dumps(call, default=str)
    posted = call.get("json")
    if posted is None:
        posted = json.loads(call["data"])
    assert posted == body and "role" not in posted
    assert DDMI_SENTINEL not in json.dumps(posted)
    assert call.get("timeout") in ((30, 900), [30, 900])


def test_a_live_call_through_the_real_transport_leaks_no_key(tmp_path, http):
    sent, _ = http
    model = llm.Round2LLM(llm.LLMCache(tmp_path, "planted_round2"), mode="live", spend=lambda: 0.0)
    out = model.call("hypothesis", MESSAGES)
    assert out["parsed"] == json.loads(ANSWER) and len(sent) == 1
    request = llm.round2_request("hypothesis", MESSAGES)
    for sentinel in (DDMI_SENTINEL, OTHER_SENTINEL):
        assert sentinel not in json.dumps(request) and sentinel not in json.dumps(out, default=str)
        for path in tmp_path.rglob("*"):
            if path.is_file():
                assert sentinel not in path.read_text(encoding="utf-8")
    assert OTHER_SENTINEL not in json.dumps(sent, default=str)


def test_a_client_error_raises_round2_api_error_without_retry_or_header(http):
    sent, queue = http
    queue.append(FakeHTTP(401, {"type": "error", "error": {"type": "authentication_error",
                                                           "message": "invalid x-api-key"}}))
    body = llm.round2_body(llm.round2_request("hypothesis", MESSAGES))
    with pytest.raises(llm.Round2APIError) as raised:
        llm._messages_transport(llm.ROUND2_API_KEY_ENV)(body)
    message = str(raised.value)
    assert "401" in message and "authentication_error" in message
    assert DDMI_SENTINEL not in message and OTHER_SENTINEL not in message
    assert len(sent) == 1


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504, 529])
def test_a_retryable_status_is_retried(http, status):
    sent, queue = http
    queue.extend([FakeHTTP(status, {"type": "error", "error": {"type": "overloaded_error", "message": "busy"}}),
                  FakeHTTP()])
    body = llm.round2_body(llm.round2_request("hypothesis", MESSAGES))
    answer = llm._messages_transport(llm.ROUND2_API_KEY_ENV)(body)
    assert answer["content"][-1]["text"] == ANSWER and len(sent) == 2


def test_at_most_two_retries(http):
    sent, queue = http
    busy = {"type": "error", "error": {"type": "overloaded_error", "message": "busy"}}
    queue.extend([FakeHTTP(529, busy), FakeHTTP(529, busy), FakeHTTP(529, busy), FakeHTTP()])
    body = llm.round2_body(llm.round2_request("hypothesis", MESSAGES))
    with pytest.raises(llm.Round2APIError):
        llm._messages_transport(llm.ROUND2_API_KEY_ENV)(body)
    assert len(sent) == 3


# ---------------------------------------------------------------- committed round-2 cache files (if any)


def _round2_cache_files():
    return sorted({path for pattern in llm.ROUND2_CACHE_GLOBS for path in ROOT.glob(pattern)})


def test_committed_round2_cache_lines_follow_s43_2():
    for path in _round2_cache_files():
        text = path.read_text(encoding="utf-8")
        assert "x-api-key" not in text.lower() and "sk" + "-ant" not in text  # fragments: the committed tree is grepped for the prefix
        for entry in cache_lines(path):
            assert set(entry) == CACHE_LINE_KEYS, path.name
            request = entry["request"]
            assert set(request) == REQUEST_KEYS and request["model"] == llm.ROUND2_MODEL, path.name
            assert entry["key"] == llm.request_key(request)
            assert entry["cost_usd"] == pytest.approx(llm.round2_call_cost(entry["usage"]), rel=1e-9, abs=1e-12)
    assert llm.round2_spend(ROOT) <= 10.0


# ---------------------------------------------------------------- S43-1, S43-2: round 1 unchanged


def test_round1_constants_are_unchanged():
    assert llm.MODEL == "deepseek-flash" and llm.BASE_URL == "https://api.deepseek.com"
    assert llm.API_KEY_ENV == "DEEPSEEK_API_KEY" and llm.MAX_TOKENS == 1500
    assert llm.INPUT_USD_PER_TOKEN == pytest.approx(0.30e-6) and llm.OUTPUT_USD_PER_TOKEN == pytest.approx(1.20e-6)
    assert llm.CACHE_DIR == ROOT / "agent_lab" / "cache"


def test_round1_request_is_unchanged(tmp_path):
    model = llm.LLM(llm.LLMCache(tmp_path), mode="replay")
    assert model.request("coder", MESSAGES) == {
        "model": "deepseek-flash", "role": "coder", "messages": MESSAGES, "max_tokens": 1500,
        "response_format": {"type": "json_object"}, "thinking": {"type": "disabled"}}


def _committed_round1_entries(pattern):
    entries = []
    for path in sorted(ROOT.glob(pattern)):
        entries += [(path.name, entry) for entry in cache_lines(path)]
    return entries


@pytest.mark.parametrize("pattern", ["agent_lab/cache/*.jsonl", "agent_lab/run/cache/*.jsonl"])
def test_every_committed_round1_request_reproduces_its_key(tmp_path, pattern):
    entries = [(name, e) for name, e in _committed_round1_entries(pattern) if not name.startswith("planted_round2")]
    assert entries
    model = llm.LLM(llm.LLMCache(tmp_path), mode="replay")
    for name, entry in entries:
        request = model.request(entry["request"]["role"], entry["request"]["messages"])
        assert request == entry["request"], name
        assert llm.request_key(request) == entry["key"], name


@pytest.mark.parametrize("files, n, total", [
    (("planted.jsonl", "planted_attempt1.jsonl", "planted_attempt2.jsonl", "planted_attempt3.jsonl"), 38, 0.032617),
    (("../run/cache/insample.jsonl",), 80, 0.127144),
    (("../run/cache/probe.jsonl",), 9, 0.002564),
])
def test_round1_cache_sums_are_unchanged(files, n, total):
    seen = {}
    for name in files:
        for entry in cache_lines(ROOT / "agent_lab" / "cache" / name):
            seen.setdefault(entry["key"], entry)
    assert len(seen) == n
    assert round(sum(float(e["cost_usd"]) for e in seen.values()), 6) == pytest.approx(total, abs=1e-9)


def test_round1_replay_answers_a_committed_request_from_its_entry(tmp_path):
    entry = cache_lines(ROOT / "agent_lab" / "run" / "cache" / "insample.jsonl")[0]
    model = llm.LLM(llm.LLMCache(ROOT / "agent_lab" / "run" / "cache", "never_written"), mode="replay")
    out = model.call(entry["request"]["role"], entry["request"]["messages"])
    assert out["cached"] is True and out["content"] == entry["response"] and out["key"] == entry["key"]
    assert not (ROOT / "agent_lab" / "run" / "cache" / "never_written.jsonl").exists()


# ---------------------------------------------------------------- S43-5: the round-2 prompts

FEATURES = {"as_of": "2019-12-27", "features": ["MOM26_1"],
            "assets": {"A1": {"MOM26_1": {"value": 0.123, "mean_104w": 0.0, "std_104w": 1.0}}}}
SNAPSHOT_TRIALS = [{"trial_id": "snap-trial-0071", "kind": "human", "rung": "M7", "is_sharpe": 0.11, "is_mdd": -0.21},
                   {"trial_id": "snap-trial-0072", "kind": "agent", "rung": "M2", "is_sharpe": -0.5, "is_mdd": -0.4,
                    "feature": {"name": "snapshot feature zeta", "expr": {"op": "cs_z", "x": {"input": "close"}}},
                    "stage": "walk_forward"}]
HISTORY_1 = {"candidate": 1, "name": "earlier candidate omega", "expr": {"op": "cs_z", "x": {"input": "close"}},
             "stage": "redundancy", "uplift": None, "p_uplift_positive": None, "survived": False}
HISTORY_2 = {"candidate": 2, "name": "earlier candidate sigma", "expr": {"op": "cs_rank", "x": {"input": "close"}},
             "stage": "invalid_spec", "uplift": None, "p_uplift_positive": None, "survived": False}
RUN_TRIALS_1 = [{"trial_id": "run-trial-0903", "kind": "agent", "rung": "M7", "is_sharpe": None, "is_mdd": None,
                 "feature": "invalid", "stage": "invalid_spec"}]
RUN_TRIALS_2 = [{"trial_id": "run-trial-0904", "kind": "agent", "rung": "M7", "is_sharpe": None, "is_mdd": None,
                 "feature": "invalid", "stage": "redundancy"}]
CACHE_1H = {"type": "ephemeral", "ttl": "1h"}


def _blocks():
    b1 = prompts.candidate_block(1, HISTORY_1, RUN_TRIALS_1)
    b2 = prompts.candidate_block(2, HISTORY_2, RUN_TRIALS_2)
    return b1, b2


def test_candidate_block_text():
    block = prompts.candidate_block(3, HISTORY_1, RUN_TRIALS_1)
    prefix = "Candidate 3 of this run: "
    assert isinstance(block, str) and block.startswith(prefix)
    assert json.loads(block[len(prefix):]) == {"candidate": HISTORY_1, "trials_logged": RUN_TRIALS_1}
    assert ": " not in block[len(prefix):] and ", " not in block[len(prefix):]  # compact JSON


def _hypothesis(blocks):
    messages = prompts.hypothesis_messages_round2(FEATURES, SNAPSHOT_TRIALS, list(blocks))
    assert len(messages) == 2
    assert messages[0]["role"] == "system" and messages[0]["content"] == prompts.LAB_BRIEF_ROUND2
    assert messages[1]["role"] == "user" and isinstance(messages[1]["content"], list)
    content = messages[1]["content"]
    assert all(block.get("type") == "text" and isinstance(block.get("text"), str) for block in content)
    assert len(content) == len(blocks) + 2
    return messages, content


@pytest.mark.parametrize("n", [0, 1, 2])
def test_hypothesis_round2_layout(n):
    blocks = _blocks()[:n]
    _, content = _hypothesis(blocks)
    stable, middle, task = content[0], content[1:-1], content[-1]
    assert stable["cache_control"] == CACHE_1H
    assert "cache_control" not in task
    assert [b["text"] for b in middle] == list(blocks)
    for k, block in enumerate(middle):
        if k == len(middle) - 1:
            assert block["cache_control"] == CACHE_1H
        else:
            assert "cache_control" not in block
    assert sum("cache_control" in block for block in content) <= 2


def test_the_stable_block_holds_the_grammar_the_summaries_and_the_snapshot_only():
    _, content = _hypothesis(_blocks())
    stable = content[0]["text"]
    assert prompts.DSL_GRAMMAR in stable
    assert "snap-trial-0071" in stable and "snap-trial-0072" in stable
    assert "0.123" in stable  # the feature summaries
    for marker in ("run-trial-0903", "run-trial-0904", "earlier candidate omega", "earlier candidate sigma",
                   "Candidate 1 of this run", "Candidate 2 of this run"):
        assert marker not in stable


def test_the_cached_prefix_is_stable_as_candidates_are_added():
    """For blocks [b1] and [b1, b2]: the stable text and b1's text are identical; only b1's marker moves to b2."""
    b1, b2 = _blocks()
    _, one = _hypothesis([b1])
    _, two = _hypothesis([b1, b2])
    strip = lambda block: {k: v for k, v in block.items() if k != "cache_control"}
    assert one[0] == two[0]
    assert strip(one[1]) == strip(two[1]) and one[1]["text"] == two[1]["text"] == b1
    assert two[2]["text"] == b2 and two[2]["cache_control"] == CACHE_1H and "cache_control" not in two[1]
    assert one[1]["cache_control"] == CACHE_1H


def test_the_stable_block_does_not_depend_on_the_run():
    b1, b2 = _blocks()
    _, none = _hypothesis([])
    _, two = _hypothesis([b1, b2])
    assert none[0] == two[0]


def test_lab_brief_round2_describes_m7():
    """S43-5 (1): the same six features and the interactions, trained on 4-week relative returns, smoothed scores."""
    brief = prompts.LAB_BRIEF_ROUND2
    assert re.search(r"4-week|four-week|four week|4 week", brief, re.IGNORECASE)
    assert re.search(r"smooth|averag", brief, re.IGNORECASE)  # each week's score smoothed (averaged) over recent weeks
    for feature in ("MOM26_1", "MOM52_4", "REV1", "VOL13", "DD13", "BETA52"):
        assert feature in brief
    messages, _ = _hypothesis(_blocks())
    assert "next week's relative return" not in text_of(messages)


def test_coder_repair_messages_show_the_exact_error_and_the_previous_answer():
    hypothesis = {"mechanism": "m", "rationale": "r", "feature_idea": "a distinctive idea phrase"}
    previous = '{"spec": {"name": "bad one", "expr": {"op": "rank_all"}}}'
    error = "unknown op 'rank_all' at expr (allowed: lag, rolling, diff)"
    messages = prompts.coder_repair_messages(hypothesis, previous, error)
    text = text_of(messages)
    assert f"The Validator refused this spec: {error}" in text
    assert previous in text or json.dumps(json.loads(previous)) in text
    assert "a distinctive idea phrase" in text


def test_round2_prompts_name_no_vendor_and_no_origin():
    b1, b2 = _blocks()
    hypothesis = {"mechanism": "m", "rationale": "r", "feature_idea": "f"}
    texts = [prompts.LAB_BRIEF_ROUND2, text_of(prompts.hypothesis_messages_round2(FEATURES, SNAPSHOT_TRIALS, [b1, b2])),
             text_of(prompts.coder_repair_messages(hypothesis, "{}", "a validator error"))]
    for text in texts:
        assert not VENDOR.search(text)
        assert not ORIGIN.search(text)
    source = (ROOT / "src" / "agents" / "prompts.py").read_text(encoding="utf-8")
    assert not VENDOR.search(source)


# Round-1 prompts: SHA-256 of the canonical JSON of each function's output on fixed inputs, computed from
# src/agents/prompts.py on main (986ca6b) before session 4.3.
ROUND1_PROMPT_HASHES = {
    "hypothesis": "776289aa73c278d5f7dfa77e1899007185fa6a0099321eea36ad0f9601073971",
    "coder": "bce01fbd938095aad80967a288b76692d1c98ec5eb42bbc971d351b345a96321",
    "skeptic": "837d0971c19770b51d08784d26e86cd55beacb06ced9396ffb731c12a170692b",
    "risk": "b09a567355896d7fb1f3b02501a5a5bfb2bde4d0cdc8426ee5f91c99f87caff0",
    "probe": "94dd246d1d7f704099304e69d3fba550b8566e347f394367f97b0ab5620a613d",
    "constants": "53f1f9bfc80479564c5f7a3b1ab39e6296005da52d416afa4af3bee7e8361c53",
}


def test_round1_prompts_are_unchanged():
    fs = {"as_of": "2019-12-27", "features": ["MOM26_1"],
          "assets": {"A1": {"MOM26_1": {"value": 0.123, "mean_104w": 0.0, "std_104w": 1.0}}}}
    hist = [{"candidate": 1, "name": "x", "expr": {"op": "cs_z", "x": {"input": "close"}}, "stage": "redundancy",
             "uplift": None, "p_uplift_positive": None, "survived": False}]
    trials = [{"trial_id": "7", "kind": "human", "rung": "M0", "is_sharpe": 0.1, "is_mdd": -0.2}]
    hyp = {"mechanism": "m", "rationale": "r", "feature_idea": "f"}
    spec = {"name": "n", "expr": {"op": "cs_z", "x": {"input": "close"}}}
    metrics = {"uplift": 0.2, "p_uplift_positive": 0.9, "rank_ic_mean": 0.01, "rank_ic_t": 1.0,
               "max_drawdown_change": 0.0, "net_sharpe": 0.3, "base_net_sharpe": 0.1}
    risk_checks = {"turnover": {"candidate": 0.5, "base": 0.6, "ratio": 0.8, "limit": 1.5},
                   "residual_beta": {"mean_abs": 0.01, "limit": 0.1},
                   "cost_sensitivity": {"adverse_uplift": 0.1, "limit": 0.0}}
    outputs = {
        "hypothesis": prompts.hypothesis_messages(fs, hist, trials),
        "coder": prompts.coder_messages(hyp),
        "skeptic": prompts.skeptic_messages(hyp, spec, {"leakage": "ok"}, metrics, 3),
        "risk": prompts.risk_messages(spec, risk_checks, metrics),
        "probe": prompts.probe_messages("A1", fs["assets"]["A1"]),
        "constants": [prompts.LAB_BRIEF, prompts.DSL_GRAMMAR, list(prompts.RISK_CONCERNS), prompts.SECTOR_ETFS],
    }
    for name, value in outputs.items():
        text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        assert hashlib.sha256(text.encode()).hexdigest() == ROUND1_PROMPT_HASHES[name], name
