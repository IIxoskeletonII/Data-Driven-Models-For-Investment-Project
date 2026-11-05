"""MCP server `ddmi-vault` (protocol section 08; decisions S33-5, S33-6, S33-9): the agents' only path to data, wrapping
src.vault.Vault.

Three tools: get_features(as_of) (anonymised summary metrics, never a series), run_walkforward(spec) (the Validator:
DSL check, leakage, warm-up, redundancy and the In-Sample walk-forward of the base rung plus the feature against the base
rung, with the §07 gate thresholds) and get_trial_history(). The In-Sample end is the constant IN_SAMPLE_END; any later
date is refused. Sectors appear as codes A1 ... A9 from a seeded permutation that never leaves the server. Every call
writes one line (tool, argument hash, ok or refused, reason; no time) to the server log, besides the vault's access log.
Every proposal gets one trial row (S33-9).

Run over stdio with `python -m src.agents.vault_server --base-rung M1` (real data, sealed vault).
"""

import argparse
import asyncio
import csv
import hashlib
import importlib.util
import json
from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pandas as pd

from src.agents.dsl import DSLError, evaluate, parse
from src.backtest import run as run_backtest
from src.config import ROOT, load_config
from src.contracts import universe
from src.metrics import performance
from src.models import tuning_spec
from src.sizing import size_book
from src.stats import paired_block_bootstrap, rank_ic
from src.vault import OOSAccessError, Vault, append_trial, logged_spec_hashes, spec_hash

IN_SAMPLE_END = "2019-12-27"  # hard-coded (§08); the server refuses to start if split.in_sample_end differs
SERVER_NAME = "ddmi-vault"
AGENT_AUTHOR = "agent lab"
AGENT_NOTES = "agent lab candidate"
LEAKAGE_CUTOFFS = ("2006-06-30", "2012-06-29", "2017-06-30")  # S33-6 (2)
LEAKAGE_SIGMA = 0.05
REDUNDANCY_MAX = 0.9  # S33-6 (4)
FEATURE_WINDOW_WEEKS = 104  # get_features: summaries over the 104 weeks ending at as_of
ADVERSE = ("costs", "bps", -1, "borrow", -1)  # the adverse scenario: last entries of costs.bps and costs.borrow
RISK_TURNOVER_RATIO_MAX = 1.5  # S33-14 (1): candidate turnover at most 1.5 times the base rung's
RISK_RESIDUAL_BETA_MAX = 0.10  # S33-14 (2): mean absolute residual beta (D10)
RISK_ADVERSE_UPLIFT_MIN = 0.0  # S33-14 (3): the adverse-cost Sharpe uplift over the base rung must stay above 0


def risk_checks(metrics: Mapping) -> dict:
    """Risk's deterministic tool checks (S33-14) on a candidate's walk-forward metrics against the base rung:
    turnover (mean weekly turnover at most 1.5 times the base rung's), residual beta (mean absolute residual beta at most
    0.10) and cost sensitivity (Sharpe uplift over the base rung under the adverse costs above 0). Absolute performance
    is not checked here (it is the Validator's gate). A missing or non-finite figure fails its check. Returns
    {"turnover": {...}, "residual_beta": {...}, "cost_sensitivity": {...}, "passed": bool, "failed": [names]}."""

    def number(key):
        value = metrics.get(key)
        return float(value) if isinstance(value, int | float | np.floating) and np.isfinite(value) else None

    turnover, base_turnover = number("mean_turnover"), number("base_mean_turnover")
    ratio = turnover / base_turnover if turnover is not None and base_turnover else None
    beta, adverse = number("mean_abs_residual_beta"), number("adverse_uplift")
    checks = {
        "turnover": {"candidate": _round(turnover), "base": _round(base_turnover), "ratio": _round(ratio),
                     "limit": RISK_TURNOVER_RATIO_MAX,
                     "passed": ratio is not None and ratio <= RISK_TURNOVER_RATIO_MAX},
        "residual_beta": {"mean_abs": _round(beta), "limit": RISK_RESIDUAL_BETA_MAX,
                          "passed": beta is not None and beta <= RISK_RESIDUAL_BETA_MAX},
        "cost_sensitivity": {"adverse_uplift": _round(adverse), "limit": RISK_ADVERSE_UPLIFT_MIN,
                             "passed": adverse is not None and adverse > RISK_ADVERSE_UPLIFT_MIN},
    }
    failed = [name for name, check in checks.items() if not check["passed"]]
    return {**checks, "passed": not failed, "failed": failed}


def anonymise(cfg: dict) -> dict[str, str]:
    """Sector -> code A1 ... A9 (S33-5): sector i of universe(cfg).sectors gets A<j+1>, j its position in
    numpy.random.default_rng(seed).permutation(9)."""
    sectors = list(universe(cfg).sectors)
    order = np.random.default_rng(int(cfg["seed"])).permutation(len(sectors))
    return {sector: f"A{int(position) + 1}" for sector, position in zip(sectors, order, strict=True)}


def _hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _round(value, digits: int = 4):
    if isinstance(value, float | np.floating):
        return None if not np.isfinite(value) else round(float(value), digits)
    return value


def load_script(filename: str):
    """A numbered pipeline script of the repository root as a module (e.g. 05_train_walkforward.py)."""
    spec = importlib.util.spec_from_file_location(filename.removesuffix(".py").replace("-", "_"), ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VaultServer:
    """The tools of `ddmi-vault` on one sealed Vault.

    cfg: the configuration; vault: a Vault sealed at IN_SAMPLE_END (or at an earlier is_end in tests); base_rung: M1, M2
    or M3 (Amendment 7 C1, S33-10); base_spec: that rung's trial spec (05_train_walkforward.model_spec), so the base
    scores reuse its trial row; trial_path: the trial log; server_log: the server's JSONL log.
    """

    def __init__(self, cfg: dict, vault: Vault, base_rung: str, base_spec: Mapping, *, trial_path: Path,
                 server_log: Path) -> None:
        if str(cfg["split"]["in_sample_end"]) != IN_SAMPLE_END:
            raise OOSAccessError(f"{SERVER_NAME}: split.in_sample_end {cfg['split']['in_sample_end']} differs from the "
                                 f"hard-coded In-Sample end {IN_SAMPLE_END} (§08)")
        if vault.is_end > pd.Timestamp(IN_SAMPLE_END):
            raise OOSAccessError(f"{SERVER_NAME}: the vault's is_end is after {IN_SAMPLE_END}")
        if base_rung not in ("M1", "M2", "M3") or base_spec.get("rung") != base_rung:
            raise ValueError(f"{SERVER_NAME}: the base rung must be M1, M2 or M3 with its own spec, got {base_rung!r}")
        self.cfg, self.vault, self.base_rung, self.base_spec = cfg, vault, base_rung, dict(base_spec)
        self.trial_path, self.server_log = Path(trial_path), Path(server_log)
        self.end = vault.is_end
        self.codes = anonymise(cfg)
        self.survivors: list[tuple[str, pd.Series]] = []
        self._inputs: dict | None = None
        self._base: dict | None = None

    # -- log -------------------------------------------------------------------------------------------------------------

    def _log(self, tool: str, argument, result: str, reason: str = "") -> None:
        self.server_log.parent.mkdir(parents=True, exist_ok=True)
        record = {"tool": tool, "argument_hash": _hash(argument)[:16], "result": result}
        if reason:
            record["reason"] = reason
        with open(self.server_log, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def _date(self, value) -> pd.Timestamp:
        day = pd.Timestamp(value)
        if day > pd.Timestamp(IN_SAMPLE_END) or day > self.end:
            raise OOSAccessError(f"{SERVER_NAME}: {day.date()} is after the In-Sample end {self.end.date()} (§08)")
        return day

    # -- shared In-Sample inputs ------------------------------------------------------------------------------------------

    def inputs(self) -> dict:
        """Closes, features, states, betas, forward returns and the weekly T-bill, all through the sealed vault."""
        if self._inputs is None:
            v, end = self.vault, self.end
            fwd, _, period = v.forward_returns(end)
            self._inputs = {"closes": v.daily_closes(end), "features": v.features(end), "states": v.market_states(end),
                            "betas": v.sizing_betas(end), "fwd": fwd, "period": period, "rf": v.tbill_weekly(end)}
        return self._inputs

    def book(self, scores: pd.DataFrame) -> dict:
        """Baseline and adverse-cost books of weekly scores (§09 sizing, Mattia's engine) and the headline figures."""
        data, costs = self.inputs(), self.cfg["costs"]
        sizing = size_book(scores, data["betas"], self.cfg)
        base = run_backtest(sizing, data["fwd"], data["period"], costs["bps_baseline"], costs["borrow_baseline"])
        adverse = run_backtest(sizing, data["fwd"], data["period"], costs["bps"][-1], costs["borrow"][-1])
        weeks = base.net.index
        rf = data["rf"].reindex(weeks)
        figures = performance(base.net, rf)
        return {"net": base.net, "adverse_net": adverse.net, "rf": rf, "scores": scores,
                "net_sharpe": figures["sharpe_rf"], "net_sharpe_zero_cost": figures["sharpe_zero_cost"],
                "max_drawdown": figures["max_drawdown"], "mean_turnover": float(base.turnover.mean()),
                "mean_abs_residual_beta": float(base.residual_beta.abs().mean()),
                "adverse_net_sharpe": performance(adverse.net, rf)["sharpe_rf"]}

    def base(self) -> dict:
        """The base rung's scores and book (its trial row already exists; a rerun adds none, S23-2)."""
        if self._base is None:
            scores = self.vault.run_walkforward(self.base_spec, trial_path=self.trial_path)
            self._base = self.book(scores)
        return self._base

    # -- get_features ------------------------------------------------------------------------------------------------------

    def get_features(self, as_of: str) -> dict:
        """Anonymised summary metrics at the last week <= as_of (S33-5): per code the six z-scored features of that week
        and their mean and standard deviation over the 104 weeks ending there, the market states of that week and the
        pooled correlation matrix of the six features over those weeks, rounded to 3 decimals. No series."""
        try:
            day = self._date(as_of)
            feats = self.vault.features(day)
            states = self.vault.market_states(day)
            closes = pd.DatetimeIndex(feats.index.get_level_values("date_close"))
            week = closes.max()
            window = closes.unique().sort_values()[-FEATURE_WINDOW_WEEKS:]
            recent = feats.loc[np.asarray(closes.isin(window))]
            asset = list(self.cfg["features"]["asset"])
            out = {"as_of": week.strftime("%Y-%m-%d"), "features": asset, "assets": {}}
            for sector, code in sorted(self.codes.items(), key=lambda item: int(item[1][1:])):
                rows = recent.xs(sector, level="ticker")[asset]
                current = feats.loc[(week, sector), asset]
                out["assets"][code] = {name: {"value": _round(current[name], 3), "mean_104w": _round(rows[name].mean(), 3),
                                              "std_104w": _round(rows[name].std(), 3)} for name in asset}
            state_row = states.loc[pd.DatetimeIndex(states.index.get_level_values("date_close")) == week].iloc[0]
            out["market_states"] = {name: _round(float(value), 3) for name, value in state_row.items()}
            corr = recent[asset].corr()
            out["feature_correlation"] = {a: {b: _round(float(corr.at[a, b]), 3) for b in asset} for a in asset}
        except Exception as error:
            self._log("get_features", as_of, "refused", f"{type(error).__name__}: {error}")
            raise
        self._log("get_features", as_of, "ok")
        return out

    # -- get_trial_history -------------------------------------------------------------------------------------------------

    def get_trial_history(self) -> list[dict]:
        """Every trial row (S33-5): human rows without params_json, agent rows with their DSL features and notes."""
        rows = []
        if self.trial_path.exists():
            with open(self.trial_path, encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    item = {"trial_id": row["trial_id"], "kind": row["kind"], "rung": row["rung"],
                            "spec_hash": row["spec_hash"][:12], "is_sharpe": row["is_sharpe"], "is_mdd": row["is_mdd"]}
                    if row["kind"] == "agent":
                        params = json.loads(row["params_json"]) if row["params_json"] else {}
                        item["agent_features"] = params.get("agent_features", params.get("invalid_dsl"))
                        item["notes"] = row["notes"]
                    rows.append(item)
        self._log("get_trial_history", {}, "ok")
        return rows

    # -- run_walkforward (the Validator, S33-6) ---------------------------------------------------------------------------

    def candidate_spec(self, feature: Mapping) -> dict:
        """The trial spec of a candidate (S33-9): the base rung's tuning plus the feature."""
        return {"rung": self.base_rung, "tuning": tuning_spec(self.cfg), "agent_features": [dict(feature)],
                "author": AGENT_AUTHOR, "kind": "agent", "notes": AGENT_NOTES}

    def _row(self, spec: Mapping, notes: dict, sharpe="", mdd="") -> None:
        digest = spec_hash(spec, self.cfg)
        if digest not in logged_spec_hashes(self.trial_path):
            append_trial({"author": AGENT_AUTHOR, "kind": "agent", "rung": self.base_rung, "spec_hash": digest,
                          "params_json": json.dumps(dict(spec), sort_keys=True, separators=(",", ":"), default=str),
                          "is_sharpe": sharpe, "is_mdd": mdd, "notes": _notes(notes)}, path=self.trial_path)

    def asset_part(self, feature) -> pd.Series:
        """The feature's asset part on the features' index (In-Sample closes)."""
        data = self.inputs()
        return evaluate(feature, data["closes"], self.cfg).reindex(data["features"].index)

    def leakage_check(self, feature) -> tuple[bool, str]:
        """S33-6 (2): values at weeks <= each cutoff are bit-identical after every later close is perturbed."""
        closes = self.inputs()["closes"]
        reference = evaluate(feature, closes, self.cfg)
        weeks = pd.DatetimeIndex(reference.index.get_level_values("date_close"))
        first, last = weeks.min() + pd.Timedelta(weeks=FEATURE_WINDOW_WEEKS + 1), weeks.max()
        cutoffs = [pd.Timestamp(day) for day in LEAKAGE_CUTOFFS if first < pd.Timestamp(day) < last]
        rng = np.random.default_rng(int(self.cfg["seed"]))
        for cutoff in cutoffs:
            perturbed = closes.copy()
            late = perturbed.index > cutoff
            perturbed.loc[late] = perturbed.loc[late].to_numpy() * np.exp(rng.normal(0, LEAKAGE_SIGMA, perturbed.loc[late].shape))
            again = evaluate(feature, perturbed, self.cfg)
            keep = np.asarray(weeks <= cutoff)
            if not np.array_equal(reference.to_numpy()[keep], again.to_numpy()[keep], equal_nan=True):
                return False, f"values at or before {cutoff.date()} change when later closes change"
        if not cutoffs:
            return False, "no leakage cutoff inside the sample"
        return True, f"bit-identical at cutoffs {[c.strftime('%Y-%m-%d') for c in cutoffs]}"

    def _scored_rows(self) -> np.ndarray:
        feats = self.inputs()["features"]
        closes = pd.DatetimeIndex(feats.index.get_level_values("date_close"))
        asset = list(self.cfg["features"]["asset"])
        return np.asarray(closes > pd.Timestamp(self.cfg["split"]["warmup_end"])) & np.isfinite(
            feats[asset].to_numpy(dtype=np.float64)).all(axis=1)

    def warmup_check(self, part: pd.Series) -> tuple[bool, str]:
        """S33-6 (3): no missing value after split.warmup_end where the six asset features are finite."""
        missing = self._scored_rows() & ~np.isfinite(part.to_numpy(dtype=np.float64))
        if missing.any():
            first = part.index[np.argmax(missing)]
            return False, f"{int(missing.sum())} missing values after the warm-up, first at {first[0].date()}"
        return True, "complete after the warm-up"

    def redundancy_check(self, part: pd.Series) -> tuple[bool, str, dict]:
        """S33-6 (4): pooled |corr| < 0.9 with the six asset features and every surviving candidate."""
        rows = self._scored_rows()
        x = part.to_numpy(dtype=np.float64)[rows]
        feats = self.inputs()["features"]
        others = {name: feats[name].to_numpy(dtype=np.float64)[rows] for name in self.cfg["features"]["asset"]}
        for k, (name, series) in enumerate(self.survivors, start=1):
            others[f"survivor {k}: {name}"] = series.to_numpy(dtype=np.float64)[rows]
        correlations = {}
        for name, y in others.items():
            with np.errstate(invalid="ignore", divide="ignore"):
                value = np.corrcoef(x, y)[0, 1] if np.std(x) > 0 and np.std(y) > 0 else np.nan
            correlations[name] = _round(float(value), 3)
            if not np.isfinite(value):
                return False, f"correlation with {name} undefined (a degenerate feature)", correlations
            if abs(value) >= REDUNDANCY_MAX:
                return False, f"|corr| = {abs(value):.3f} >= {REDUNDANCY_MAX} with {name}", correlations
        return True, f"max |corr| = {max(abs(v) for v in correlations.values()):.3f}", correlations

    def metrics(self, candidate: dict) -> dict:
        """Candidate against the base rung on their common weeks (S33-5): headline Sharpe, uplift, drawdown change,
        bootstrap P(uplift > 0), rank IC, turnover, residual beta, adverse-cost figures and the §07 gate verdict."""
        base, sel, data = self.base(), self.cfg["selection"], self.inputs()
        weeks = candidate["net"].index.intersection(base["net"].index)
        boot = paired_block_bootstrap(candidate["net"].loc[weeks], base["net"].loc[weeks],
                                      n_resamples=int(sel["bootstrap_resamples"]), block=int(sel["bootstrap_block"]),
                                      seed=int(self.cfg["seed"]), rf=data["rf"].reindex(weeks))
        c_perf = performance(candidate["net"].loc[weeks], data["rf"].reindex(weeks))
        b_perf = performance(base["net"].loc[weeks], data["rf"].reindex(weeks))
        a_c = performance(candidate["adverse_net"].loc[weeks], data["rf"].reindex(weeks))["sharpe_rf"]
        a_b = performance(base["adverse_net"].loc[weeks], data["rf"].reindex(weeks))["sharpe_rf"]
        scores = candidate["scores"]
        ic = rank_ic(scores, data["fwd"].reindex(scores.index)[list(scores.columns)])
        uplift = c_perf["sharpe_rf"] - b_perf["sharpe_rf"]
        mdd_change = c_perf["max_drawdown"] - b_perf["max_drawdown"]
        passed = bool(uplift >= float(sel["sharpe_uplift"]) and mdd_change >= -float(sel["mdd_tolerance"])
                      and boot["p_uplift_positive"] >= float(sel["bootstrap_prob"]))
        return {"weeks": len(weeks), "net_sharpe": c_perf["sharpe_rf"], "net_sharpe_zero_cost": c_perf["sharpe_zero_cost"],
                "base_net_sharpe": b_perf["sharpe_rf"], "uplift": uplift, "max_drawdown": c_perf["max_drawdown"],
                "max_drawdown_change": mdd_change, "p_uplift_positive": boot["p_uplift_positive"],
                "rank_ic_mean": ic["mean"], "rank_ic_t": ic["t_stat"], "mean_turnover": candidate["mean_turnover"],
                "base_mean_turnover": base["mean_turnover"], "mean_abs_residual_beta": candidate["mean_abs_residual_beta"],
                "adverse_net_sharpe": a_c, "adverse_uplift": a_c - a_b, "passed_gate": passed}

    def run_walkforward(self, spec, candidate: int | None = None, cost_usd: float | None = None) -> dict:
        """The Validator (S33-6) on one proposed DSL spec; writes the proposal's trial row (S33-9). Returns stage reached,
        checks, rounded metrics (when the walk-forward ran) and `passed` (all checks and the gate)."""
        notes = {"candidate": candidate, "cost_usd": _round(cost_usd, 6) if cost_usd is not None else None}
        result = {"candidate": candidate, "checks": {}, "metrics": None, "passed": False}
        try:
            feature = parse(spec)
        except DSLError as error:
            invalid = {"invalid_dsl": spec}
            self._row(invalid, {**notes, "stage": "invalid_spec"})
            self._log("run_walkforward", spec, "refused", f"DSLError: {error}")
            return {**result, "stage": "invalid_spec", "reason": str(error), "spec_hash": spec_hash(invalid, self.cfg)}
        feature_dict = {"name": feature.name, "expr": feature.expr}
        model_spec = self.candidate_spec(feature_dict)
        result["spec_hash"] = spec_hash(model_spec, self.cfg)
        try:
            ok, reason = self.leakage_check(feature)
            result["checks"]["leakage"] = reason
            stage = "leakage"
            if ok:
                part = self.asset_part(feature)
                ok, reason = self.warmup_check(part)
                result["checks"]["warm_up"], stage = reason, "warm_up"
            if ok:
                ok, reason, correlations = self.redundancy_check(part)
                result["checks"]["redundancy"], stage = reason, "redundancy"
                result["checks"]["correlations"] = correlations
            if not ok:
                self._row(model_spec, {**notes, "stage": stage, "reason": reason})
                self._log("run_walkforward", spec, "ok", f"rejected at {stage}")
                return {**result, "stage": stage, "reason": reason}
            computed: dict = {}

            def evaluate_scores(scores: pd.DataFrame):
                computed.update(self.metrics(self.book(scores)))
                summary = {**notes, "stage": "walk_forward", **{k: _round(computed[k], 4) for k in (
                    "uplift", "p_uplift_positive", "rank_ic_mean", "mean_turnover", "mean_abs_residual_beta")},
                    "passed_gate": computed["passed_gate"]}
                return computed["net_sharpe"], computed["max_drawdown"], _notes(summary)

            self.vault.run_walkforward(model_spec, evaluate_scores, trial_path=self.trial_path)
        except Exception as error:
            self._log("run_walkforward", spec, "refused", f"{type(error).__name__}: {error}")
            raise
        result.update(stage="walk_forward", metrics={k: _round(v) for k, v in computed.items()},
                      risk_checks=risk_checks(computed), passed=bool(computed["passed_gate"]),
                      reason="passed the §07 gate against the base rung" if computed["passed_gate"] else
                      "failed the §07 gate against the base rung")
        self._log("run_walkforward", spec, "ok", result["reason"])
        return result

    def mark_survivor(self, spec) -> None:
        """Record a candidate that survived the Validator, Skeptic and Risk, for later redundancy checks (S33-6 (4))."""
        feature = parse(spec)
        self.survivors.append((feature.name, self.asset_part(feature)))


def _notes(values: dict) -> str:
    return json.dumps(values, sort_keys=True, separators=(",", ":"), default=str)


# -- MCP --------------------------------------------------------------------------------------------------------------------


def build_mcp(core: VaultServer):
    """The MCP server `ddmi-vault` with the three tools of §08 (mcp 2.x MCPServer), each calling `core`."""
    from mcp.server.mcpserver import MCPServer

    server = MCPServer(SERVER_NAME, instructions="In-Sample research vault: anonymised summaries only (protocol §08).")

    @server.tool(name="get_features", description="Anonymised feature summaries at a date <= the In-Sample end.")
    def tool_get_features(as_of: str) -> dict:
        return core.get_features(as_of)

    @server.tool(name="run_walkforward", description="Validate a DSL feature spec and run the In-Sample walk-forward.")
    def tool_run_walkforward(spec: dict, candidate: int | None = None, cost_usd: float | None = None) -> dict:
        return core.run_walkforward(spec, candidate=candidate, cost_usd=cost_usd)

    @server.tool(name="get_trial_history", description="Every trial so far, summary columns only.")
    def tool_get_trial_history() -> dict:
        return {"trials": core.get_trial_history()}

    return server


def call_tool(server, name: str, arguments: dict) -> dict:
    """Call a tool of the MCP server in process and return its structured result (raises on a tool error)."""
    result = asyncio.run(server.call_tool(name, arguments))
    if getattr(result, "isError", False) or getattr(result, "is_error", False):
        text = " ".join(getattr(part, "text", "") for part in getattr(result, "content", []))
        raise RuntimeError(f"{SERVER_NAME}.{name}: {text}")
    structured = getattr(result, "structuredContent", None) or getattr(result, "structured_content", None)
    if structured is None:
        text = "".join(getattr(part, "text", "") for part in result.content)
        structured = json.loads(text)
    return structured.get("result", structured) if set(structured) == {"result"} else structured


# -- module-level tools of contract 17 (the real-data server once `serve` or `use` has set it) ---------------------------

_DEFAULT: VaultServer | None = None


def use(core: VaultServer) -> None:
    global _DEFAULT
    _DEFAULT = core


def _default() -> VaultServer:
    if _DEFAULT is None:
        raise RuntimeError(f"{SERVER_NAME}: no server configured; build a VaultServer and call use(), or run the module")
    return _DEFAULT


def get_features(as_of: str) -> dict:
    """Anonymised summary metrics at the last week <= as_of (S33-5)."""
    return _default().get_features(as_of)


def run_walkforward(spec: Mapping[str, object]) -> dict:
    """The Validator and the In-Sample walk-forward of a DSL feature spec (S33-5, S33-6); one trial row per proposal."""
    return _default().run_walkforward(spec)


def get_trial_history() -> list[dict]:
    """Every trial logged so far (summary columns only)."""
    return _default().get_trial_history()


def real_server(base_rung: str, cfg: dict | None = None, *, run_dir: Path = ROOT / "agent_lab" / "insample") -> VaultServer:
    """The server on the real In-Sample data (data/processed, data/raw/fred), the trial log docs/trial_log.csv."""
    cfg = load_config() if cfg is None else cfg
    vault = Vault(pd.Timestamp(IN_SAMPLE_END), lock_path=ROOT / "FROZEN.lock",
                  log_path=ROOT / "outputs" / "vault_access_log.jsonl",
                  data_dir=ROOT / cfg["data"]["data_dir"] / "processed", raw_dir=ROOT / cfg["data"]["data_dir"] / "raw",
                  cfg=cfg)
    base_spec = load_script("05_train_walkforward.py").model_spec(base_rung, cfg)
    return VaultServer(cfg, vault, base_rung, base_spec, trial_path=ROOT / "docs" / "trial_log.csv",
                       server_log=run_dir / "vault_server_log.jsonl")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-rung", required=True, choices=("M1", "M2", "M3"))
    args = parser.parse_args(argv)
    core = real_server(args.base_rung)
    use(core)
    build_mcp(core).run("stdio")


if __name__ == "__main__":
    main()
