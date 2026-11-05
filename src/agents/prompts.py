"""Prompts of the LLM roles of the research lab (protocol section 08; decision S33-7): Hypothesis, Coder, Skeptic, Risk.

Prompts hold no time or machine-dependent field; numbers are rounded (metrics to 2 decimals, feature summaries to 3), so
a replay on another machine rebuilds the same requests. The agents see anonymised codes A1 ... A9 and summary metrics
only, never a price series.
"""

import json
import math

LAB_BRIEF = (
    "You are a quantitative researcher in a small research lab. The lab studies a weekly strategy that ranks 9 "
    "anonymised US sector ETFs (codes A1 to A9) after each Friday close; the top 2 are bought and the bottom 2 sold the "
    "next Monday, with a market hedge. A model (the base rung) already ranks them on six features: MOM26_1 (26-week "
    "momentum skipping the last week), MOM52_4 (12-1 month momentum), REV1 (last week's return), VOL13 (13-week daily "
    "volatility), DD13 (drawdown from the 13-week high) and BETA52 (52-week market beta), each z-scored across the 9 "
    "sectors every Friday. Your job is to propose ONE new feature with an economic mechanism that could improve the "
    "cross-sectional ranking beyond these six. Features are computed only from past weekly prices, so they cannot "
    "use the future. You never trade and you never see raw prices. Always answer with one JSON object."
)

DSL_GRAMMAR = (
    "Feature DSL (JSON, no code). A spec is {\"name\": str, \"expr\": node}. Leaves: {\"input\": \"close\"} (the "
    "sector's weekly close, a total-return index) and {\"input\": \"spy\"} (the S&P 500's weekly close, the same for "
    "every sector). Operations, every window ending at the current week t, n in weeks: "
    "{\"op\": \"lag\", \"n\": 1-104, \"x\": node}; {\"op\": \"rolling\", \"stat\": \"mean\"|\"std\"|\"sum\"|\"min\"|"
    "\"max\", \"n\": 2-104, \"x\": node}; {\"op\": \"diff\", \"n\": 1-104, \"x\": node} (x(t) - x(t-n)); "
    "{\"op\": \"log\", \"x\": node}; {\"op\": \"ratio\", \"a\": node, \"b\": node}; {\"op\": \"cs_z\", \"x\": node} and "
    "{\"op\": \"cs_rank\", \"x\": node} (z-score or rank across the 9 sectors each week); {\"op\": \"mul_state\", "
    "\"state\": S or [S1, S2], \"x\": node} with S in BEAR24 (1 after a negative 2-year market return, else 0), MKT_VAR "
    "(126-day market variance), VIX, TERM (10y-3m yield spread), CREDIT (BAA-10y spread). Rules: the root must be cs_z "
    "or cs_rank, or mul_state whose child is cs_z or cs_rank; mul_state only at the root (a market state alone cannot "
    "reorder sectors, so it can only scale a cross-sectional feature); at most 25 nodes and depth 10. Example, the "
    "weekly log return: {\"op\": \"diff\", \"n\": 1, \"x\": {\"op\": \"log\", \"x\": {\"input\": \"close\"}}}."
)


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _r(value, digits: int = 2):
    return None if value is None else round(float(value), digits)


def history_lines(records: list[dict]) -> list[dict]:
    """Earlier candidates of this run, as the agents may see them: name, expression, stage reached, uplift, P, verdict."""
    lines = []
    for record in records:
        spec = record.get("spec") if isinstance(record.get("spec"), dict) else {}
        metrics = record.get("metrics") or {}
        lines.append({"candidate": record["candidate"], "name": spec.get("name"), "expr": spec.get("expr"),
                      "stage": record.get("stage"), "uplift": _r(metrics.get("uplift")),
                      "p_uplift_positive": _r(metrics.get("p_uplift_positive")), "survived": record.get("survived")})
    return lines


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, 2) if math.isfinite(number) else None


def trial_summaries(trials: list[dict]) -> list[dict]:
    """Every logged trial as Hypothesis sees it (S33-15 (4)): trial id, kind, rung, headline Sharpe and max drawdown
    (2 decimals); agent rows add the feature's name and expression (or "invalid") and the stage reached."""
    lines = []
    for row in trials:
        item = {"trial_id": row.get("trial_id"), "kind": row.get("kind"), "rung": row.get("rung"),
                "is_sharpe": _number(row.get("is_sharpe")), "is_mdd": _number(row.get("is_mdd"))}
        if row.get("kind") == "agent":
            features = row.get("agent_features")
            first = features[0] if isinstance(features, list) and features and isinstance(features[0], dict) else None
            item["feature"] = {"name": first.get("name"), "expr": first.get("expr")} if first else "invalid"
            try:
                notes = json.loads(row.get("notes") or "{}")
            except ValueError:
                notes = {}
            item["stage"] = notes.get("stage") if isinstance(notes, dict) else None
        lines.append(item)
    return lines


def hypothesis_messages(features_summary: dict, history: list[dict], trials: list[dict] = ()) -> list[dict]:
    task = ("Propose one new feature idea. Use the summaries below only as context; do not repeat an earlier candidate "
            "or a close variant of one. Answer with the JSON object {\"mechanism\": str (why the feature should predict "
            "next week's relative return across sectors), \"rationale\": str (why it is not already captured by the six "
            "features), \"feature_idea\": str (how to compute it from weekly closes, the S&P 500 and the market states)}.")
    return [{"role": "system", "content": LAB_BRIEF},
            {"role": "user", "content": f"{DSL_GRAMMAR}\n\nFeature summaries at the end of the research sample "
                                        f"(anonymised): {_json(features_summary)}\n\nTrial history (every trial "
                                        f"logged so far: the model ladder and earlier proposals): "
                                        f"{_json(list(trials))}\n\nEarlier candidates of this run: "
                                        f"{_json(history)}\n\n{task}"}]


def coder_messages(hypothesis: dict) -> list[dict]:
    task = ("Translate the feature idea into exactly one spec of the DSL. Use only the operations listed. Answer with "
            "the JSON object {\"spec\": {\"name\": str, \"expr\": node}}.")
    return [{"role": "system", "content": "You translate feature ideas into a JSON feature DSL. " + DSL_GRAMMAR},
            {"role": "user", "content": f"Feature idea: {_json(hypothesis)}\n\n{task}"}]


def skeptic_messages(hypothesis: dict, spec: dict, checks: dict, metrics: dict, n_candidates: int) -> list[dict]:
    shown = {key: _r(metrics.get(key)) for key in ("uplift", "p_uplift_positive", "rank_ic_mean", "rank_ic_t",
                                                  "max_drawdown_change", "net_sharpe", "base_net_sharpe")}
    task = (f"You are the lab's skeptic. This candidate passed the deterministic checks (no look-ahead, complete after "
            f"the warm-up, |correlation| below 0.9 with existing features) and the walk-forward gate against the base "
            f"rung (Sharpe uplift >= 0.15, drawdown at most 2 points worse, bootstrap P(uplift > 0) >= 0.80). It is "
            f"candidate {n_candidates} of this run, and every candidate tried counts against the final result. Attack "
            f"it on overfitting, redundancy with the six features and economic plausibility. Veto only for a concrete "
            f"reason, not merely because the effect is modest. Answer with the JSON object {{\"veto\": true|false, "
            f"\"reasons\": str}}.")
    return [{"role": "system", "content": LAB_BRIEF},
            {"role": "user", "content": f"Hypothesis: {_json(hypothesis)}\nSpec: {_json(spec)}\nChecks: {_json(checks)}\n"
                                        f"In-Sample walk-forward against the base rung: {_json(shown)}\n\n{task}"}]


RISK_CONCERNS = ("concentration", "mechanism", "instability")  # S33-14: the only grounds of a Risk LLM veto


def risk_messages(spec: dict, checks: dict, metrics: dict) -> list[dict]:
    """The Risk LLM's review (S33-14): it runs only after the tool's three checks passed; it sees those checks and the
    rank IC, never an absolute Sharpe ratio, and may veto only for a named concern of RISK_CONCERNS."""
    shown = {"tool_checks_passed": {
                 "turnover_vs_base_rung": {"candidate": _r(checks["turnover"]["candidate"]),
                                           "base_rung": _r(checks["turnover"]["base"]),
                                           "ratio": _r(checks["turnover"]["ratio"]), "limit": checks["turnover"]["limit"]},
                 "mean_abs_residual_beta": {"value": _r(checks["residual_beta"]["mean_abs"]),
                                            "limit": checks["residual_beta"]["limit"]},
                 "sharpe_uplift_over_base_rung_adverse_costs": {"value": _r(checks["cost_sensitivity"]["adverse_uplift"]),
                                                                "limit": checks["cost_sensitivity"]["limit"]}},
             "rank_ic_mean": _r(metrics.get("rank_ic_mean"), 4), "rank_ic_t": _r(metrics.get("rank_ic_t"))}
    task = ("You are the lab's risk officer. The deterministic tool has already checked turnover, residual market beta "
            "and cost sensitivity, each against the base rung, and all three passed; absolute performance is judged by "
            "the walk-forward gate, not by you. Veto only for a concrete risk concern that the figures cannot show: "
            "\"concentration\" (the feature would concentrate the book in the same few sectors or one exposure), "
            "\"mechanism\" (the feature's construction is flawed or its signal is an artefact), or \"instability\" (the "
            "feature is likely to behave erratically or break across regimes). A veto that names no such concern, or "
            "that rests on Sharpe ratios or costs, does not count, so do not cite Sharpe ratios, costs or the tool's "
            "figures in your notes. Answer with the JSON object {\"veto\": true|false, "
            "\"concern\": \"concentration\"|\"mechanism\"|\"instability\"|null, \"notes\": str}.")
    return [{"role": "system", "content": "You are a risk officer reviewing a proposed trading feature. Answer in JSON."},
            {"role": "user", "content": f"Spec: {_json(spec)}\nRisk review inputs: {_json(shown)}\n\n{task}"}]


SECTOR_ETFS = {"XLB": "Materials", "XLE": "Energy", "XLF": "Financials", "XLI": "Industrials", "XLK": "Technology",
               "XLP": "Consumer Staples", "XLU": "Utilities", "XLV": "Health Care", "XLY": "Consumer Discretionary"}


def probe_messages(code: str, summary: dict) -> list[dict]:
    """The recognition probe (S33-17): one anonymised code's six features at the In-Sample end, as get_features gives
    them; the model names the sector ETF it believes the code is."""
    task = (f"The summary below describes one US sector ETF, anonymised as {code}, at the end of December 2019. Which of "
            f"these ETFs is it: {_json(SECTOR_ETFS)}? Answer with the JSON object {{\"ticker\": one of the nine tickers, "
            f"\"reason\": str}}.")
    return [{"role": "system", "content": "You are a quantitative analyst. Answer in JSON."},
            {"role": "user", "content": f"Features of {code} (z-scored across the nine sectors each week; value at the "
                                        f"last week, mean and standard deviation over the last 104 weeks): "
                                        f"{_json(summary)}\n\n{task}"}]
