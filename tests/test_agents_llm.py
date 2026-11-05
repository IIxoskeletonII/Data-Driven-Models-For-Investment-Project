"""LLM client, hashed cache and budget meter of the lab (src/agents/llm.py; decisions S33-1, S33-7). A fake client
stands in for the API: no network, no key."""

import json
from types import SimpleNamespace

import pytest

from src.agents import llm

SENTINEL_KEY = "sk-test-SENTINEL-0123456789abcdef"
MESSAGES = [{"role": "system", "content": "Answer in json."}, {"role": "user", "content": "Propose a feature."}]


class FakeClient:
    def __init__(self, content='{"ok": true}', prompt_tokens=1000, completion_tokens=200):
        self.calls = []
        self.content, self.prompt_tokens, self.completion_tokens = content, prompt_tokens, completion_tokens
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        usage = SimpleNamespace(model_dump=lambda: {"prompt_tokens": self.prompt_tokens,
                                                    "completion_tokens": self.completion_tokens,
                                                    "total_tokens": self.prompt_tokens + self.completion_tokens,
                                                    "prompt_tokens_details": {"cached_tokens": 0}})
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


def make(tmp_path, mode="live", client=None, budget=5.0, run="test"):
    client = client or FakeClient()
    model = llm.LLM(llm.LLMCache(tmp_path, run), mode=mode, budget_usd=budget, client_factory=lambda: client)
    return model, client


def test_cost_uses_the_peak_prices_of_s33_1():
    assert llm.call_cost({"prompt_tokens": 1_000_000, "completion_tokens": 0}) == pytest.approx(0.30)
    assert llm.call_cost({"prompt_tokens": 0, "completion_tokens": 1_000_000}) == pytest.approx(1.20)
    assert llm.call_cost({"prompt_tokens": 1000, "completion_tokens": 200}) == pytest.approx(0.00054)


def test_request_key_ignores_dict_order():
    a = {"model": "m", "messages": [{"role": "user", "content": "x"}], "max_tokens": 10}
    b = {"max_tokens": 10, "messages": [{"content": "x", "role": "user"}], "model": "m"}
    assert llm.request_key(a) == llm.request_key(b)


def test_live_call_is_cached_with_its_cost_and_parameters(tmp_path):
    model, client = make(tmp_path)
    out = model.call("hypothesis", MESSAGES)
    assert out["parsed"] == {"ok": True} and not out["cached"] and out["cost_usd"] == pytest.approx(0.00054)
    sent = client.calls[0]
    assert sent["model"] == "deepseek-flash" and sent["response_format"] == {"type": "json_object"}
    assert sent["extra_body"] == {"thinking": {"type": "disabled"}} and "temperature" not in sent
    lines = (tmp_path / "test.jsonl").read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[0])
    assert set(entry) == {"key", "request", "response", "usage", "cost_usd"}
    assert entry["key"] == llm.request_key(entry["request"]) and entry["usage"]["prompt_tokens"] == 1000
    assert model.live_calls == 1 and model.run_cost == pytest.approx(0.00054)


def test_a_cached_request_costs_nothing_and_does_not_call_the_api(tmp_path):
    model, _ = make(tmp_path)
    model.call("coder", MESSAGES)
    again, client2 = make(tmp_path)
    out = again.call("coder", MESSAGES)
    assert out["cached"] and out["cost_usd"] == 0.0 and client2.calls == [] and again.cached_calls == 1


def test_replay_needs_no_client_and_raises_on_a_missing_request(tmp_path):
    model, _ = make(tmp_path)
    model.call("skeptic", MESSAGES)

    def no_client():
        raise AssertionError("replay must not build a client")

    replay = llm.LLM(llm.LLMCache(tmp_path), mode="replay", client_factory=no_client)
    assert replay.call("skeptic", MESSAGES)["parsed"] == {"ok": True}
    with pytest.raises(llm.ReplayMiss):
        replay.call("risk", MESSAGES)


def test_the_budget_stops_before_the_call(tmp_path):
    model, client = make(tmp_path, budget=0.001)  # worst case: ~33 chars × 0.3e-6 + 1500 × 1.2e-6 = 0.0018 > 0.001
    with pytest.raises(llm.BudgetExceeded):
        model.call("hypothesis", MESSAGES)
    assert client.calls == [] and not (tmp_path / "test.jsonl").exists()


def test_the_budget_counts_every_cache_file(tmp_path):
    earlier = {"key": "0" * 64, "request": {}, "response": "{}", "usage": {}, "cost_usd": 4.999}
    (tmp_path / "planted.jsonl").write_text(json.dumps(earlier) + "\n", encoding="utf-8")
    model, client = make(tmp_path, run="insample")
    assert model.cache.total_cost() == pytest.approx(4.999)
    with pytest.raises(llm.BudgetExceeded):
        model.call("hypothesis", MESSAGES)
    assert client.calls == []


def test_blank_or_non_json_content_parses_to_none(tmp_path):
    model, _ = make(tmp_path, client=FakeClient(content="   "))
    assert model.call("risk", MESSAGES)["parsed"] is None
    assert llm.parse_json("[1, 2]") is None and llm.parse_json('{"veto": false}') == {"veto": False}


def test_the_api_key_never_reaches_a_cache_file(tmp_path, monkeypatch):
    monkeypatch.setenv(llm.API_KEY_ENV, SENTINEL_KEY)
    model, _ = make(tmp_path)
    model.call("hypothesis", MESSAGES)
    model.call("coder", MESSAGES + [{"role": "user", "content": "again"}])
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert SENTINEL_KEY not in path.read_text(encoding="utf-8")


def test_the_real_client_needs_the_key_only_for_live_calls(monkeypatch):
    monkeypatch.delenv(llm.API_KEY_ENV, raising=False)
    with pytest.raises(RuntimeError, match="not set"):
        llm._openai_client()


def test_unknown_mode_is_refused(tmp_path):
    with pytest.raises(ValueError):
        llm.LLM(llm.LLMCache(tmp_path), mode="dry")


# ---------------------------------------------------------------- S33-13: the parser takes only the first complete object


def test_parse_json_takes_the_first_complete_object_and_refuses_other_text():
    assert llm.parse_json('{"spec": {"name": "a", "expr": {}}}}}') == {"spec": {"name": "a", "expr": {}}}
    assert llm.parse_json('{"a": 1}\n } ] ') == {"a": 1}
    for text in ('{"a": 1} and more', 'note: {"a": 1}', '{"a": 1}{"b": 2}', '{"a": ', "", "   ", "[1]", None):
        assert llm.parse_json(text) is None


def test_the_dsl_schema_stays_strict_after_the_lenient_parse():
    """A spec rescued from surplus braces still goes through the strict DSL validation (S33-3)."""
    from src.agents import dsl

    close = {"input": "close"}
    rescued = [
        '{"spec": {"name": "u", "expr": {"op": "cs_z", "x": {"op": "rank_all", "x": {"input": "close"}}}}}}}',  # unknown op
        '{"spec": {"name": "k", "expr": {"op": "cs_z", "x": {"input": "close"}}, "extra": 1}}}',  # extra spec key
        '{"spec": {"name": "n", "expr": {"op": "cs_z", "x": {"op": "lag", "n": 2, "k": 3, "x": {"input": "close"}}}}}}',
        '{"spec": {"name": "m", "expr": {"op": "lag", "n": 1, "x": {"input": "close"}}}}}',  # root rule
    ]
    for text in rescued:
        parsed = llm.parse_json(text)
        assert parsed is not None
        with pytest.raises(dsl.DSLError):
            dsl.parse(parsed["spec"])
    assert llm.parse_json('{"spec": {"name": "t", "expr": {"op": "cs_z", "x": ') is None  # truncated
    valid = '{"spec": {"name": "ok", "expr": {"op": "cs_z", "x": ' + json.dumps(close) + '}}}}}'
    assert dsl.parse(llm.parse_json(valid)["spec"]).name == "ok"
