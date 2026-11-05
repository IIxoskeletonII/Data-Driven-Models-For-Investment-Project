"""The planted-signal test of the research lab (decisions S33-8, S33-12 and S33-15).

Written from the decisions and the public interface only. The replay tests rerun the planted run from the committed cache
(agent_lab/cache/planted.jsonl) in a temporary folder, with no API key and no network, and compare it with the committed
agent_lab/planted/summary.json. They fail, and do not skip, when either committed file is missing: CI must not pass
without the committed run. The other tests are fast: the base-rung rule, the PASS rule and the two replay refusals.
"""

import json
import re

import pytest

from src.agents import llm
from src.agents.vault_server import load_script
from src.config import ROOT

LAB = load_script("04_agent_lab.py")
CACHE_FILE = ROOT / "agent_lab" / "cache" / "planted.jsonl"
SUMMARY_FILE = ROOT / "agent_lab" / "planted" / "summary.json"
FORBIDDEN = re.compile(r"planted|injected|noise", re.IGNORECASE)
TOLERANCE = 1e-6
CANDIDATE_FIELDS = ("source", "stage", "survived", "passed_validator")
CANDIDATE_NUMBERS = ("uplift", "p_uplift_positive", "abs_corr_planted")


def _contents(messages) -> str:
    return "\n".join(str(m.get("content", "")) for m in messages)


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _llm_written_with_a_forbidden_word() -> list[str]:
    """String values longer than 20 characters of the LLMs' own answers (cached responses) that contain a forbidden word, e.g. a Hypothesis that
    says "noise"; a later prompt may quote them. Only these model-written strings are exempt (S33-15)."""
    found = []
    for line in CACHE_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                answer = json.loads(json.loads(line)["response"])
            except ValueError:
                continue
            found += [s for s in _strings(answer) if len(s) > 20 and FORBIDDEN.search(s)]  # never a bare word
    return found


def _lab_written(text: str, exempt: list[str]) -> str:
    """The prompt text with the exempt model-written strings removed (raw and as JSON-escaped)."""
    for value in sorted(exempt, key=len, reverse=True):
        text = text.replace(json.dumps(value, ensure_ascii=False)[1:-1], "").replace(value, "")
    return text


def _snapshot(folder):
    if not folder.exists():
        return None
    return sorted((str(p.relative_to(folder)), p.stat().st_size, p.stat().st_mtime_ns) for p in folder.rglob("*"))


# ---------------------------------------------------------------- the replayed run (slow, once per module)


@pytest.fixture(scope="module")
def replay(tmp_path_factory):
    assert CACHE_FILE.exists(), f"{CACHE_FILE} is missing: the committed planted run is required"
    assert SUMMARY_FILE.exists(), f"{SUMMARY_FILE} is missing: the committed planted run is required"
    base = tmp_path_factory.mktemp("planted_replay")
    recorded = []
    original = llm.LLM.call

    def recording(self, *args, **kwargs):
        messages = args[1] if len(args) > 1 else kwargs.get("messages")
        recorded.append([dict(m) for m in messages])
        return original(self, *args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(llm.LLM, "call", recording)
        summary = LAB.run_planted(mode="replay", run_dir=base / "run", data_root=base / "data")
    committed = json.loads(SUMMARY_FILE.read_text(encoding="utf-8"))
    return summary, committed, recorded


def test_committed_run_files_exist():
    assert CACHE_FILE.exists(), f"{CACHE_FILE} is missing"
    assert SUMMARY_FILE.exists(), f"{SUMMARY_FILE} is missing"


def test_replay_passes(replay):
    summary, _, _ = replay
    assert summary["pass"] is True
    assert summary["planted_survived"] is True
    assert summary["noise_survivors"] == []
    assert summary["live_calls"] == 0


def test_replay_reproduces_the_committed_summary(replay):
    summary, committed, _ = replay
    for key in ("base_rung", "counts", "pass", "unaided_discovery"):
        assert summary[key] == committed[key], key
    for rung, value in committed.get("base_net_sharpes", {}).items():
        assert summary["base_net_sharpes"][rung] == pytest.approx(value, abs=TOLERANCE), rung
    assert len(summary["candidates"]) == len(committed["candidates"])
    for ours, theirs in zip(summary["candidates"], committed["candidates"], strict=True):
        assert ours["candidate"] == theirs["candidate"]
        for key in CANDIDATE_FIELDS:
            assert ours[key] == theirs[key], (theirs["candidate"], key)
        for key in CANDIDATE_NUMBERS:
            if theirs.get(key) is None:
                assert ours.get(key) is None, (theirs["candidate"], key)
            else:
                assert ours[key] == pytest.approx(theirs[key], abs=TOLERANCE), (theirs["candidate"], key)


def test_no_prompt_of_the_replay_names_an_origin(replay):
    summary, _, recorded = replay
    assert recorded, "no LLM call was recorded"
    sources = {c["source"] for c in summary["candidates"] if c["source"] != "llm"}
    exempt = _llm_written_with_a_forbidden_word()
    for messages in recorded:
        text = _contents(messages)
        assert not FORBIDDEN.search(_lab_written(text, exempt))
        assert not any(source in text for source in sources)


def test_no_committed_request_names_an_origin():
    assert CACHE_FILE.exists(), f"{CACHE_FILE} is missing"
    lines = [line for line in CACHE_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines
    exempt = _llm_written_with_a_forbidden_word()
    for line in lines:
        text = _contents(json.loads(line)["request"]["messages"])
        assert "injected:" not in text
        assert not FORBIDDEN.search(_lab_written(text, exempt))


# ---------------------------------------------------------------- S33-15 (3): a replay never writes into agent_lab/


@pytest.mark.parametrize("run_dir", [ROOT / "agent_lab" / "planted", ROOT / "agent_lab" / "replay_probe_of_the_tests"])
def test_replay_refuses_to_write_into_agent_lab(tmp_path, run_dir):
    before = _snapshot(run_dir)
    data_root = tmp_path / "data"
    with pytest.raises(ValueError):
        LAB.run_planted(mode="replay", run_dir=run_dir, data_root=data_root)
    assert _snapshot(run_dir) == before
    assert not data_root.exists() or not any(data_root.iterdir()), "data was built before the refusal"


def test_replay_needs_out():
    with pytest.raises(SystemExit):
        LAB.main(["--planted", "--replay"])


# ---------------------------------------------------------------- Amendment 7 C1: the base rung


@pytest.mark.parametrize(("sharpes", "expected"), [
    ({"M1": -1.105, "M2": -1.178, "M3": -1.077}, "M3"),
    ({"M1": 0.40, "M2": 0.55, "M3": 0.10}, "M2"),
    ({"M1": 0.90, "M2": 0.55, "M3": 0.10}, "M1"),
    ({"M1": 0.50, "M2": 0.50, "M3": 0.50}, "M1"),
    ({"M1": 0.20, "M2": 0.50, "M3": 0.50}, "M2"),
    ({"M1": 0.50, "M2": 0.20, "M3": 0.50}, "M1"),
])
def test_choose_base_rung(sharpes, expected):
    assert LAB.choose_base_rung(sharpes) == expected


# ---------------------------------------------------------------- S33-8: the PASS rule


def _record(candidate, source, survived):
    return {"candidate": candidate, "source": source, "survived": survived}


def test_pass_when_the_planted_feature_survives_and_nothing_unrelated_does():
    records = [_record(1, "llm", False), _record(2, "llm", False), _record(3, "injected:planted", True),
               _record(4, "injected:noise1", False)]
    verdict = LAB.planted_verdict(records, {1: 0.02, 2: None, 3: 1.0, 4: 0.01})
    assert verdict["pass"] is True
    assert verdict["planted_survived"] is True
    assert not verdict["noise_survivors"]
    assert verdict["unaided_discovery"] is False


def test_fail_when_the_planted_feature_is_rejected():
    records = [_record(1, "llm", False), _record(2, "injected:planted", False), _record(3, "injected:noise1", False)]
    verdict = LAB.planted_verdict(records, {1: 0.02, 2: 1.0, 3: 0.01})
    assert verdict["pass"] is False
    assert verdict["planted_survived"] is False


@pytest.mark.parametrize("survivor", [_record(1, "llm", True), _record(1, "injected:noise1", True)])
def test_fail_when_an_unrelated_candidate_survives(survivor):
    records = [survivor, _record(2, "injected:planted", True)]
    verdict = LAB.planted_verdict(records, {1: 0.3, 2: 1.0})
    assert verdict["pass"] is False
    assert verdict["planted_survived"] is True
    assert verdict["noise_survivors"]


@pytest.mark.parametrize("corr", [0.5, 0.75, -0.6])
def test_a_survivor_related_to_the_planted_feature_does_not_fail_it(corr):
    records = [_record(1, "llm", True), _record(2, "injected:planted", True), _record(3, "injected:noise2", False)]
    verdict = LAB.planted_verdict(records, {1: corr, 2: 1.0, 3: 0.0})
    assert verdict["pass"] is True
    assert not verdict["noise_survivors"]


def test_unaided_discovery_is_an_llm_record_close_to_the_planted_feature():
    records = [_record(1, "llm", False), _record(2, "llm", False), _record(3, "injected:planted", True)]
    verdict = LAB.planted_verdict(records, {1: 0.95, 2: 0.1, 3: 1.0})
    assert verdict["unaided_discovery"] is True
    assert verdict["pass"] is True


def test_the_injected_planted_record_is_not_an_unaided_discovery():
    records = [_record(1, "llm", False), _record(2, "injected:planted", True), _record(3, "injected:noise1", False)]
    verdict = LAB.planted_verdict(records, {1: 0.85, 2: 1.0, 3: 0.95})
    assert verdict["unaided_discovery"] is False
