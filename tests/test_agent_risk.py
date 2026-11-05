"""Risk role of the research lab (decision S33-14): the deterministic risk checks, the parsing of the Risk answer into
a veto, and the Risk prompt, which must not show absolute Sharpe figures. No network, no key."""

import math

import pytest

from src.agents.graph import risk_verdict
from src.agents.prompts import RISK_CONCERNS, risk_messages
from src.agents.vault_server import RISK_ADVERSE_UPLIFT_MIN, RISK_RESIDUAL_BETA_MAX, RISK_TURNOVER_RATIO_MAX, risk_checks

PASSING = {"mean_turnover": 0.30, "base_mean_turnover": 0.25, "mean_abs_residual_beta": 0.05, "adverse_uplift": 0.10}


def _metrics(**overrides):
    out = dict(PASSING)
    out.update(overrides)
    return out


# ---------------------------------------------------------------- risk_checks


def test_constants():
    assert RISK_TURNOVER_RATIO_MAX == 1.5
    assert RISK_RESIDUAL_BETA_MAX == 0.10
    assert RISK_ADVERSE_UPLIFT_MIN == 0.0


def test_all_pass_structure_and_limits():
    out = risk_checks(PASSING)
    assert out["passed"] is True
    assert out["failed"] == []
    assert set(out["turnover"]) == {"candidate", "base", "ratio", "limit", "passed"}
    assert set(out["residual_beta"]) == {"mean_abs", "limit", "passed"}
    assert set(out["cost_sensitivity"]) == {"adverse_uplift", "limit", "passed"}
    assert out["turnover"]["limit"] == RISK_TURNOVER_RATIO_MAX
    assert out["residual_beta"]["limit"] == RISK_RESIDUAL_BETA_MAX
    assert out["cost_sensitivity"]["limit"] == RISK_ADVERSE_UPLIFT_MIN
    assert out["turnover"]["ratio"] == pytest.approx(1.2)
    assert all(out[k]["passed"] is True for k in ("turnover", "residual_beta", "cost_sensitivity"))


@pytest.mark.parametrize(
    "overrides, check, passed",
    [
        ({"mean_turnover": 0.375, "base_mean_turnover": 0.25}, "turnover", True),  # ratio exactly 1.5
        ({"mean_turnover": 0.38, "base_mean_turnover": 0.25}, "turnover", False),
        ({"mean_abs_residual_beta": 0.10}, "residual_beta", True),
        ({"mean_abs_residual_beta": 0.1001}, "residual_beta", False),
        ({"adverse_uplift": 0.0}, "cost_sensitivity", False),
        ({"adverse_uplift": -0.2}, "cost_sensitivity", False),
        ({"adverse_uplift": 1e-6}, "cost_sensitivity", True),
    ],
)
def test_thresholds(overrides, check, passed):
    out = risk_checks(_metrics(**overrides))
    assert out[check]["passed"] is passed
    assert out["failed"] == ([] if passed else [check])
    assert out["passed"] is passed


@pytest.mark.parametrize("bad", ["missing", None, math.nan, math.inf, -math.inf])
@pytest.mark.parametrize(
    "key, check",
    [
        ("mean_turnover", "turnover"),
        ("base_mean_turnover", "turnover"),
        ("mean_abs_residual_beta", "residual_beta"),
        ("adverse_uplift", "cost_sensitivity"),
    ],
)
def test_non_finite_or_missing_figure_fails_its_check(key, check, bad):
    metrics = _metrics()
    if bad == "missing":
        del metrics[key]
    else:
        metrics[key] = bad
    out = risk_checks(metrics)
    assert out[check]["passed"] is False
    assert out["failed"] == [check]
    assert out["passed"] is False


def test_zero_base_turnover_fails():
    out = risk_checks(_metrics(base_mean_turnover=0.0))
    assert out["turnover"]["passed"] is False
    assert out["failed"] == ["turnover"]


def test_failed_order_and_empty_input():
    bad = {"mean_turnover": 1.0, "base_mean_turnover": 0.1, "mean_abs_residual_beta": 0.5, "adverse_uplift": -1.0}
    assert risk_checks(bad)["failed"] == ["turnover", "residual_beta", "cost_sensitivity"]
    empty = risk_checks({})
    assert empty["failed"] == ["turnover", "residual_beta", "cost_sensitivity"]
    assert empty["passed"] is False


def test_absolute_performance_is_not_checked():
    assert risk_checks(_metrics(net_sharpe=-5.0, adverse_net_sharpe=-3.0)) == risk_checks(PASSING)


def test_display_rounding():
    out = risk_checks({"mean_turnover": 0.123456, "base_mean_turnover": 0.111111, "mean_abs_residual_beta": 0.0543219,
                       "adverse_uplift": 0.0123456})
    assert out["turnover"]["candidate"] == 0.1235
    assert out["turnover"]["base"] == 0.1111
    assert out["turnover"]["ratio"] == round(0.123456 / 0.111111, 4)
    assert out["residual_beta"]["mean_abs"] == 0.0543
    assert out["cost_sensitivity"]["adverse_uplift"] == 0.0123


def test_display_none_when_not_finite():
    out = risk_checks({"mean_turnover": math.nan, "base_mean_turnover": None, "adverse_uplift": math.inf})
    assert out["turnover"]["candidate"] is None
    assert out["turnover"]["base"] is None
    assert out["turnover"]["ratio"] is None
    assert out["residual_beta"]["mean_abs"] is None
    assert out["cost_sensitivity"]["adverse_uplift"] is None


# ---------------------------------------------------------------- risk_verdict


def test_concerns():
    assert RISK_CONCERNS == ("concentration", "mechanism", "instability")


@pytest.mark.parametrize("parsed", [None, "not a dict", ["veto"], {}, {"concern": "mechanism"}, {"veto": "true"},
                                    {"veto": 1}, {"veto": None}])
def test_unparseable_counts_as_veto(parsed):
    out = risk_verdict(parsed, "garbled")
    assert out["veto"] is True
    assert out["by"] == "llm"
    assert out["llm_veto"] is None
    assert out["notes"].startswith("unparseable answer counted as a veto")


def test_no_veto():
    out = risk_verdict({"veto": False, "concern": None, "notes": "Sharpe and costs look fine"}, "{}")
    assert out["veto"] is False
    assert out["llm_veto"] is False
    assert out["by"] == "llm"
    assert "invalid_veto" not in out
    assert {"veto", "by", "concern", "notes", "llm_veto"} <= set(out)


@pytest.mark.parametrize("concern", RISK_CONCERNS)
@pytest.mark.parametrize("notes", ["two sectors carry the whole score", "costly to explain", "a borrowed idea",
                                   "the sharpest move"])
def test_valid_veto(concern, notes):
    out = risk_verdict({"veto": True, "concern": concern, "notes": notes}, "{}")
    assert out["veto"] is True
    assert out["llm_veto"] is True
    assert "invalid_veto" not in out
    assert out["concern"] == concern
    assert out["notes"] == notes


@pytest.mark.parametrize("parsed", [
    {"veto": True, "concern": None, "notes": "unstable"},
    {"veto": True, "notes": "unstable"},
    {"veto": True, "concern": "costs", "notes": "unstable"},
    {"veto": True, "concern": "Concentration", "notes": "unstable"},
    {"veto": True, "concern": "other", "notes": "unstable"},
])
def test_veto_with_invalid_concern_is_overruled(parsed):
    out = risk_verdict(parsed, "{}")
    assert out["veto"] is False
    assert out["llm_veto"] is True
    assert isinstance(out["invalid_veto"], str)


@pytest.mark.parametrize("notes", ["Sharpe falls after the change", "the SHARPE ratio drops", "cost is high",
                                   "costs eat the edge", "borrow is expensive"])
def test_veto_citing_performance_or_costs_is_overruled(notes):
    out = risk_verdict({"veto": True, "concern": "mechanism", "notes": notes}, "{}")
    assert out["veto"] is False
    assert out["llm_veto"] is True
    assert isinstance(out["invalid_veto"], str)
    assert out["notes"] == notes
    assert out["concern"] == "mechanism"


# ---------------------------------------------------------------- risk_messages

SPEC = {"name": "mom_x_vol", "expression": "MOM26_1 * VOL13", "rationale": "momentum scaled by recent volatility"}
METRICS = _metrics(net_sharpe=-0.9637, base_net_sharpe=0.3211, adverse_net_sharpe=-2.3456)


def _contents():
    messages = risk_messages(SPEC, risk_checks(METRICS), METRICS)
    assert isinstance(messages, list) and messages
    assert all({"role", "content"} <= set(m) for m in messages)
    return messages, "\n".join(m["content"] for m in messages)


def test_messages_hide_absolute_sharpe():
    _, text = _contents()
    for needle in ("-0.96", "0.32", "-2.35", "2.3456", "0.9637", "net_sharpe_baseline_costs", "adverse_net_sharpe"):
        assert needle not in text


def test_messages_name_concerns_and_keys():
    _, text = _contents()
    for word in RISK_CONCERNS:
        assert word in text
    for key in ('"veto"', '"concern"', '"notes"'):
        assert key in text


def test_messages_deterministic():
    assert _contents()[0] == _contents()[0]
