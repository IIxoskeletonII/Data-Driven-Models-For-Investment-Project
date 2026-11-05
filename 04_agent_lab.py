"""Run the multi-agent research lab of protocol section 08: the planted-signal test first (decisions S33-8, S33-12), then
at most ~40 In-Sample candidates behind the vault (S33-5 to S33-9). Every LLM call is cached under agent_lab/cache/ and
--replay reproduces a run offline with no API key.

Planted-signal test (--planted): a synthetic market with one planted effect (src/agents/planted.py) is built into
outputs/agent_lab/planted_data/ (git-ignored, regenerated deterministically); its base rung is chosen by Amendment 7 C1;
6 LLM candidates run, then the planted spec and 4 noise specs are injected at the Validator. PASS: the planted feature
survives, and every candidate whose asset part has |corr| < 0.5 with the planted one is rejected. Whether the LLM agents
proposed the planted feature (or one with |corr| >= 0.9 to it) unaided is reported as information only.

In-Sample run (--insample, S33-10, S33-16): base rung M2, 40 LLM candidates, no injected specs. docs/trial_log.csv is
copied at the start to agent_lab/run/trial_log_snapshot.csv; Hypothesis sees that snapshot plus this run's own trials.
Every proposal is a docs/trial_log.csv row (kind "agent"). Budget: USD 5 minus the planted runs' cached spend. A failed
call is resumed by running the same command again (the snapshot is kept, cached answers replay at zero cost). Then
--probe runs the recognition probe (S33-17), and agent_lab/run/review.md lists every surviving candidate for the human
gate (no M5 before Eliya and Mattia approve features by name).

Inputs:  synthetic market (planted test); data/processed/ and data/raw/fred through src/vault.py (In-Sample run)
Outputs: agent_lab/cache/<run>.jsonl, agent_lab/planted/ (candidates.jsonl, trial_log.csv, summary.json,
         vault_server_log.jsonl); agent_lab/run/ (cache/insample.jsonl, cache/probe.jsonl, trial_log_snapshot.csv,
         candidates.jsonl, summary.json, probe.json, review.md, run_log.jsonl, vault_server_log.jsonl) and
         docs/trial_log.csv rows (kind "agent")
"""

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from src.agents import planted, prompts
from src.agents.graph import Lab
from src.agents.llm import CACHE_DIR, LLM, LLMCache
from src.agents.vault_server import IN_SAMPLE_END, VaultServer, load_script, real_server
from src.config import ROOT, load_config
from src.vault import Vault

PLANTED_LLM_CANDIDATES = 6  # S33-8
PLANTED_RUN = "planted"
PASS_CORR = 0.5  # S33-8: candidates with |corr| < 0.5 to the planted feature must be rejected
UNAIDED_CORR = 0.9  # S33-8: information only
BASE_RUNGS = ("M1", "M2", "M3")
INSAMPLE_BASE_RUNG = "M2"  # S33-10
RUN_DIR = ROOT / "agent_lab" / "run"  # S33-16
INSAMPLE_RUN, PROBE_RUN = "insample", "probe"
TRIAL_LOG = ROOT / "docs" / "trial_log.csv"


def choose_base_rung(sharpes: dict[str, float]) -> str:
    """Amendment 7 C1: the highest In-Sample headline net Sharpe among M1, M2, M3; exact ties to the simpler rung."""
    best = max(sharpes[r] for r in BASE_RUNGS)
    return next(r for r in BASE_RUNGS if sharpes[r] == best)


def planted_vault(cfg: dict, data_root: Path) -> tuple[Vault, dict]:
    paths = planted.build_data_dir(data_root, cfg)
    vault = Vault(pd.Timestamp(cfg["split"]["in_sample_end"]), lock_path=paths["lock"],
                  log_path=data_root / "vault_access_log.jsonl", data_dir=paths["processed"], raw_dir=paths["raw"], cfg=cfg)
    return vault, paths


def planted_correlations(core: VaultServer, records: list[dict]) -> dict[int, float | None]:
    """|corr| of each valid candidate's asset part with the planted feature's, on the rows the Validator checks."""
    rows = core._scored_rows()
    reference = core.asset_part(planted.PLANTED_SPEC).to_numpy(dtype=np.float64)[rows]
    out = {}
    for record in records:
        if record.get("stage") == "invalid_spec":
            out[record["candidate"]] = None
            continue
        values = core.asset_part(record["spec"]).to_numpy(dtype=np.float64)[rows]
        finite = np.isfinite(values) & np.isfinite(reference)
        if finite.sum() < 3 or np.std(values[finite]) == 0:
            out[record["candidate"]] = None
            continue
        out[record["candidate"]] = round(abs(float(np.corrcoef(values[finite], reference[finite])[0, 1])), 4)
    return out


def planted_verdict(records: list[dict], correlations: dict[int, float | None]) -> dict:
    """PASS/FAIL of S33-8 and the unaided-discovery information."""
    planted_records = [r for r in records if r["source"] == "injected:planted"]
    planted_ok = bool(planted_records) and planted_records[0]["survived"]
    noise_survivors = [r["candidate"] for r in records if r["source"] != "injected:planted" and r["survived"]
                       and (correlations.get(r["candidate"]) is None or abs(correlations[r["candidate"]]) < PASS_CORR)]
    unaided = [r["candidate"] for r in records if r["source"] == "llm" and correlations.get(r["candidate"]) is not None
               and abs(correlations[r["candidate"]]) >= UNAIDED_CORR]
    return {"pass": bool(planted_ok and not noise_survivors), "planted_survived": planted_ok,
            "noise_survivors": noise_survivors, "unaided_discovery": bool(unaided), "unaided_candidates": unaided}


def counts(records: list[dict]) -> dict:
    validated = [r for r in records if r.get("passed_validator")]
    vetoed = [r for r in validated if not r["survived"]]
    return {"proposed": len(records), "validated": len(validated), "vetoed": len(vetoed),
            "surviving": sum(r["survived"] for r in records)}


def run_planted(*, mode: str, run_dir: Path, data_root: Path, cache_dir: Path = CACHE_DIR) -> dict:
    """The planted-signal test (S33-8, S33-12); writes run_dir/{candidates.jsonl, trial_log.csv, summary.json,
    vault_server_log.jsonl} and returns the summary. The trial log and server log start empty. A replay refuses to
    write into agent_lab/, which holds the committed runs (S33-15 (3))."""
    cfg = planted.planted_cfg()
    run_dir = Path(run_dir)
    if mode == "replay" and run_dir.resolve().is_relative_to((ROOT / "agent_lab").resolve()):
        raise ValueError(f"a replay may not write into agent_lab/ (committed runs): {run_dir}; pass another --out")
    run_dir.mkdir(parents=True, exist_ok=True)
    for name in ("trial_log.csv", "vault_server_log.jsonl", "candidates.jsonl"):
        (run_dir / name).unlink(missing_ok=True)
    if Path(data_root).exists():
        shutil.rmtree(data_root)
    vault, _ = planted_vault(cfg, Path(data_root))
    w05 = load_script("05_train_walkforward.py")
    trial_path, server_log = run_dir / "trial_log.csv", run_dir / "vault_server_log.jsonl"
    sharpes = {}
    for rung in BASE_RUNGS:
        probe = VaultServer(cfg, vault, rung, w05.model_spec(rung, cfg), trial_path=trial_path, server_log=server_log)
        sharpes[rung] = float(probe.base()["net_sharpe"])
    base = choose_base_rung(sharpes)
    core = VaultServer(cfg, vault, base, w05.model_spec(base, cfg), trial_path=trial_path, server_log=server_log)
    model = LLM(LLMCache(cache_dir, PLANTED_RUN), mode=mode, budget_usd=float(cfg["agent_lab"]["budget_usd"]))
    injected = [{"source": "injected:planted", "spec": planted.PLANTED_SPEC}] + [
        {"source": f"injected:noise{k}", "spec": spec} for k, spec in enumerate(planted.NOISE_SPECS, start=1)]
    lab = Lab(core, model, run_dir, n_llm=PLANTED_LLM_CANDIDATES, injected=injected, cfg=cfg)
    outcome = lab.run()
    records = outcome["records"]
    correlations = planted_correlations(core, records)
    summary = {"run": PLANTED_RUN, "mode": mode, "kappa": planted.KAPPA, "base_rung": base,
               "base_net_sharpes": {r: round(s, 6) for r, s in sharpes.items()}, **planted_verdict(records, correlations),
               "counts": counts(records), "stopped": outcome["stopped"],
               "spend_usd_this_run": round(model.run_cost, 6), "live_calls": model.live_calls,
               "cached_calls": model.cached_calls, "total_cache_spend_usd": round(model.cache.total_cost(), 6),
               "candidates": [{"candidate": r["candidate"], "source": r["source"],
                               "name": r["spec"].get("name") if isinstance(r.get("spec"), dict) else None,
                               "stage": r["stage"], "passed_validator": r.get("passed_validator", False),
                               "skeptic_veto": r.get("skeptic", {}).get("veto"), "risk_veto": r.get("risk", {}).get("veto"),
                               "risk_by": r.get("risk", {}).get("by"),
                               "risk_invalid_veto": r.get("risk", {}).get("invalid_veto"),
                               "survived": r["survived"], "abs_corr_planted": correlations.get(r["candidate"]),
                               "uplift": (r.get("metrics") or {}).get("uplift"),
                               "p_uplift_positive": (r.get("metrics") or {}).get("p_uplift_positive")} for r in records]}
    deterministic = {k: v for k, v in summary.items() if k not in ("mode", "spend_usd_this_run", "live_calls",
                                                                    "cached_calls")}
    with open(run_dir / "summary.json", "w", encoding="utf-8", newline="\n") as handle:
        json.dump(deterministic, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
    return summary


# -- the real In-Sample run (S33-10, S33-16), the recognition probe (S33-17) and the review ---------------------------------


def lab_budget(cfg: dict) -> float:
    """S33-16: agent_lab.budget_usd minus the spend already cached by the planted runs (agent_lab/cache/)."""
    return float(cfg["agent_lab"]["budget_usd"]) - LLMCache(CACHE_DIR, "planted").total_cost()


def _trial_keys(path: Path) -> list[tuple[str, str]]:
    import csv

    with open(path, encoding="utf-8", newline="") as handle:
        return [(row["trial_id"], row["spec_hash"]) for row in csv.DictReader(handle)]


def insample_paths(mode: str, run_dir: Path) -> dict:
    """Snapshot, trial log and cache folder of an In-Sample run (S33-16). Live: run_dir must be agent_lab/run; the first
    invocation copies docs/trial_log.csv to the snapshot, a resumption keeps it (and checks the trial log still starts
    with it); a finished run (summary.json present) is refused. Replay: run_dir outside agent_lab/; the committed
    snapshot is copied there as both snapshot and trial log, so docs/trial_log.csv is never written."""
    run_dir = Path(run_dir)
    committed = RUN_DIR / "trial_log_snapshot.csv"
    if mode == "replay":
        if run_dir.resolve().is_relative_to((ROOT / "agent_lab").resolve()):
            raise ValueError(f"a replay may not write into agent_lab/ (committed runs): {run_dir}; pass another --out")
        if not committed.exists():
            raise FileNotFoundError(f"{committed} is missing: no committed In-Sample run to replay")
        run_dir.mkdir(parents=True, exist_ok=True)
        for name in ("trial_log_snapshot.csv", "trial_log.csv"):
            shutil.copyfile(committed, run_dir / name)
        return {"run_dir": run_dir, "snapshot": run_dir / "trial_log_snapshot.csv", "trial_path": run_dir / "trial_log.csv",
                "cache_dir": RUN_DIR / "cache", "resumed": False}
    if run_dir.resolve() != RUN_DIR.resolve():
        raise ValueError(f"a live In-Sample run writes only {RUN_DIR}, got {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)
    if (run_dir / "summary.json").exists():
        raise SystemExit(f"{run_dir / 'summary.json'} exists: the In-Sample run is complete and is not run again")
    resumed = committed.exists()
    if resumed:
        snapshot_keys = _trial_keys(committed)
        if _trial_keys(TRIAL_LOG)[:len(snapshot_keys)] != snapshot_keys:
            raise RuntimeError("docs/trial_log.csv no longer starts with the run's snapshot; resumption refused (S33-16)")
    else:
        shutil.copyfile(TRIAL_LOG, committed)
    with open(run_dir / "run_log.jsonl", "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps({"mode": mode, "resumed": resumed}, sort_keys=True) + "\n")
    return {"run_dir": run_dir, "snapshot": committed, "trial_path": TRIAL_LOG, "cache_dir": run_dir / "cache",
            "resumed": resumed}


def insample_counts(records: list[dict]) -> dict:
    """proposed, invalid (invalid spec), refused (refused or tool error), validated, vetoed, surviving."""
    return {**counts(records), "invalid": sum(r.get("stage") == "invalid_spec" for r in records),
            "refused": sum(r.get("stage") in ("refused", "tool_error") for r in records)}


def run_insample(*, mode: str, run_dir: Path = RUN_DIR) -> dict:
    """The real In-Sample run (S33-16); writes run_dir/{candidates.jsonl, summary.json, review.md} and returns the
    summary with this invocation's spend and call counts."""
    cfg = load_config()
    paths = insample_paths(mode, run_dir)
    run_dir = paths["run_dir"]
    core = real_server(INSAMPLE_BASE_RUNG, cfg, run_dir=run_dir, trial_path=paths["trial_path"],
                       history_snapshot=paths["snapshot"])
    model = LLM(LLMCache(paths["cache_dir"], INSAMPLE_RUN), mode=mode, budget_usd=lab_budget(cfg))
    lab = Lab(core, model, run_dir, n_llm=int(cfg["agent_lab"]["max_candidates"]), cfg=cfg)
    outcome = lab.run()
    records = outcome["records"]
    # spend and calls of this run's own cache file only (cache/insample.jsonl), so a replay reports the same figures
    # after the probe has added cache/probe.jsonl
    run_entries = ([json.loads(line) for line in model.cache.path.read_text(encoding="utf-8").splitlines() if line.strip()]
                   if model.cache.path.exists() else [])
    summary = {"run": INSAMPLE_RUN, "base_rung": INSAMPLE_BASE_RUNG, "base_net_sharpe": round(float(core.base()["net_sharpe"]), 6),
               "counts": insample_counts(records), "stopped": outcome["stopped"], "budget_usd": round(lab_budget(cfg), 6),
               "total_cache_spend_usd": round(sum(float(e.get("cost_usd", 0.0)) for e in run_entries), 6),
               "llm_calls_cached": len(run_entries),
               "candidates": [{"candidate": r["candidate"],
                               "name": r["spec"].get("name") if isinstance(r.get("spec"), dict) else None,
                               "stage": r["stage"], "passed_validator": r.get("passed_validator", False),
                               "skeptic_veto": r.get("skeptic", {}).get("veto"), "risk_veto": r.get("risk", {}).get("veto"),
                               "risk_by": r.get("risk", {}).get("by"), "survived": r["survived"],
                               "uplift": (r.get("metrics") or {}).get("uplift"),
                               "p_uplift_positive": (r.get("metrics") or {}).get("p_uplift_positive")} for r in records]}
    with open(run_dir / "summary.json", "w", encoding="utf-8", newline="\n") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
    write_review(run_dir)
    return {**summary, "mode": mode, "resumed": paths["resumed"], "spend_usd_this_run": round(model.run_cost, 6),
            "live_calls": model.live_calls, "cached_calls": model.cached_calls}


def run_probe(*, mode: str, run_dir: Path = RUN_DIR) -> dict:
    """The recognition probe (S33-17): one call per code with its anonymised features at the In-Sample end; writes
    run_dir/probe.json and rewrites review.md. A replay reads the committed cache and needs run_dir outside agent_lab/."""
    run_dir = Path(run_dir)
    if mode == "replay" and run_dir.resolve().is_relative_to((ROOT / "agent_lab").resolve()):
        raise ValueError(f"a replay may not write into agent_lab/ (committed runs): {run_dir}; pass another --out")
    run_dir.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    core = real_server(INSAMPLE_BASE_RUNG, cfg, run_dir=run_dir, trial_path=TRIAL_LOG)
    features = core.get_features(IN_SAMPLE_END)
    truth = {code: sector for sector, code in core.codes.items()}
    model = LLM(LLMCache(RUN_DIR / "cache", PROBE_RUN), mode=mode, budget_usd=lab_budget(cfg))
    results = []
    for code in sorted(features["assets"], key=lambda c: int(c[1:])):
        answer = model.call("probe", prompts.probe_messages(code, features["assets"][code]))
        parsed = answer["parsed"] or {}
        ticker = parsed.get("ticker") if isinstance(parsed.get("ticker"), str) else None
        results.append({"code": code, "answer": ticker, "hit": ticker == truth[code],
                        "reason": str(parsed.get("reason", answer["content"]))[:300]})
    hits = sum(r["hit"] for r in results)
    probe = {"n": len(results), "hits": hits, "hit_rate": round(hits / len(results), 4),
             "chance": round(1 / len(results), 4), "results": results}
    with open(run_dir / "probe.json", "w", encoding="utf-8", newline="\n") as handle:
        json.dump(probe, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
    if (run_dir / "candidates.jsonl").exists():
        write_review(run_dir)
    return {**probe, "spend_usd_this_run": round(model.run_cost, 6), "live_calls": model.live_calls,
            "cached_calls": model.cached_calls, "total_cache_spend_usd": round(model.cache.total_cost(), 6)}


def _f(value, digits: int = 2) -> str:
    return "n/a" if value is None else f"{float(value):.{digits}f}"


def write_review(run_dir: Path) -> Path:
    """agent_lab/run/review.md (S33-9, Session 3.3 step 7): counts, every surviving candidate with its DSL spec,
    mechanism, metrics against the base rung and the Skeptic and Risk notes, every candidate in one table, the probe."""
    run_dir = Path(run_dir)
    records = [json.loads(line) for line in (run_dir / "candidates.jsonl").read_text(encoding="utf-8").splitlines()
               if line.strip()]
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    c = summary["counts"]
    lines = ["# Agent lab: In-Sample review", "",
             f"Base rung {summary['base_rung']} (S33-10; In-Sample headline net Sharpe {_f(summary['base_net_sharpe'], 3)}). "
             f"Proposed {c['proposed']}, invalid {c['invalid']}, refused {c['refused']}, validated {c['validated']}, "
             f"vetoed {c['vetoed']}, surviving {c['surviving']}. LLM spend of the run: USD "
             f"{summary['total_cache_spend_usd']:.6f} over {summary['llm_calls_cached']} cached calls"
             + (f"; stopped: {summary['stopped']}" if summary.get("stopped") else "") + ".", "",
             ("A surviving candidate passed the Validator (leakage, warm-up, redundancy, the §07 gate against the base rung "
             "on the same weeks) and neither the Skeptic nor Risk (tool checks, then LLM) vetoed it. No candidate enters "
             "M5 until Eliya and Mattia approve it by name (Session 3.3 step 7)."), "", "## Surviving candidates", ""]
    survivors = [r for r in records if r.get("survived")]
    if not survivors:
        lines += ["None.", ""]
    for r in survivors:
        m, h = r.get("metrics") or {}, r.get("hypothesis") or {}
        lines += [f"### Candidate {r['candidate']}: {r['spec'].get('name')}", "",
                  f"- DSL spec: `{json.dumps(r['spec'], sort_keys=True, ensure_ascii=False)}`",
                  f"- Spec hash: `{r.get('spec_hash')}`",
                  f"- Mechanism: {h.get('mechanism', 'n/a')}",
                  f"- Rationale: {h.get('rationale', 'n/a')}",
                  (f"- Uplift vs {summary['base_rung']}: {_f(m.get('uplift'), 3)} (net Sharpe {_f(m.get('net_sharpe'))} against "
                  f"{_f(m.get('base_net_sharpe'))}); P(uplift > 0) {_f(m.get('p_uplift_positive'), 3)}; max drawdown change "
                  f"{_f(m.get('max_drawdown_change'))}"),
                  f"- Rank IC: mean {_f(m.get('rank_ic_mean'), 4)}, t {_f(m.get('rank_ic_t'))}",
                  (f"- Turnover: {_f(m.get('mean_turnover'))} a week (base {_f(m.get('base_mean_turnover'))}); mean "
                  f"|residual beta| {_f(m.get('mean_abs_residual_beta'), 4)}; adverse-cost uplift {_f(m.get('adverse_uplift'))}"),
                  f"- Skeptic: {r.get('skeptic', {}).get('reasons', 'n/a')}",
                  f"- Risk ({r.get('risk', {}).get('by')}): {r.get('risk', {}).get('notes', 'n/a')}", ""]
    lines += ["## Every candidate", "", "| # | Name | Stage | Uplift | P | Skeptic veto | Risk veto | Survived |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in records:
        m = r.get("metrics") or {}
        name = r["spec"].get("name") if isinstance(r.get("spec"), dict) and "name" in r["spec"] else "(invalid)"
        lines.append(f"| {r['candidate']} | {str(name).replace('|', '/')} | {r.get('stage')} | {_f(m.get('uplift'), 3)} | "
                     f"{_f(m.get('p_uplift_positive'), 3)} | {r.get('skeptic', {}).get('veto', '')} | "
                     f"{r.get('risk', {}).get('veto', '')} | {r.get('survived')} |")
    probe_path = run_dir / "probe.json"
    lines += ["", "## Recognition probe (S33-17)", ""]
    if probe_path.exists():
        probe = json.loads(probe_path.read_text(encoding="utf-8"))
        lines += [(f"Hit rate {probe['hits']}/{probe['n']} ({probe['hit_rate']:.2f}; chance {probe['chance']:.2f}): a measured "
                  "residual of the anonymisation, which changes nothing in the run."), "",
                  "| Code | Answer | Hit |", "| --- | --- | --- |"]
        lines += [f"| {r['code']} | {r['answer']} | {r['hit']} |" for r in probe["results"]]
    else:
        lines.append("Not run yet.")
    path = run_dir / "review.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--planted", action="store_true", help="run the planted-signal test (S33-8)")
    group.add_argument("--insample", action="store_true", help="run the real In-Sample lab (S33-16)")
    group.add_argument("--probe", action="store_true", help="run the recognition probe (S33-17)")
    parser.add_argument("--replay", action="store_true", help="answer every LLM call from the committed cache (no key)")
    parser.add_argument("--out", type=Path, default=None, help="run folder (needed with --replay)")
    args = parser.parse_args(argv)
    if args.replay and args.out is None:
        raise SystemExit("--replay needs --out: the default folders in agent_lab/ hold the committed runs (S33-15)")
    mode = "replay" if args.replay else "live"
    if args.insample:
        s = run_insample(mode=mode, run_dir=args.out or RUN_DIR)
        c = s["counts"]
        print(f"In-Sample lab (base rung {s['base_rung']}): proposed {c['proposed']}, invalid {c['invalid']}, refused "
              f"{c['refused']}, validated {c['validated']}, vetoed {c['vetoed']}, surviving {c['surviving']}; stopped: "
              f"{s['stopped']}")
        print(f"spend this invocation USD {s['spend_usd_this_run']:.6f}; live calls {s['live_calls']}, cached "
              f"{s['cached_calls']}; run cache USD {s['total_cache_spend_usd']:.6f}; resumed {s['resumed']}")
        return
    if args.probe:
        s = run_probe(mode=mode, run_dir=args.out or RUN_DIR)
        print(f"recognition probe: {s['hits']}/{s['n']} hits (hit rate {s['hit_rate']}, chance {s['chance']}); spend USD "
              f"{s['spend_usd_this_run']:.6f}, live calls {s['live_calls']}, cached {s['cached_calls']}")
        return
    if args.replay and args.out is None:
        raise SystemExit("--replay needs --out: the default folder agent_lab/planted holds the committed run (S33-15)")
    run_dir = args.out or ROOT / "agent_lab" / PLANTED_RUN
    summary = run_planted(mode="replay" if args.replay else "live", run_dir=run_dir,
                          data_root=ROOT / "outputs" / "agent_lab" / "planted_data")
    c = summary["counts"]
    print(f"planted-signal test: {'PASS' if summary['pass'] else 'FAIL'} (base rung {summary['base_rung']}); "
          f"proposed {c['proposed']}, validated {c['validated']}, vetoed {c['vetoed']}, surviving {c['surviving']}")
    print(f"unaided discovery (information only): {summary['unaided_discovery']} {summary['unaided_candidates']}")
    print(f"spend this run USD {summary['spend_usd_this_run']:.6f}; live calls {summary['live_calls']}, cached "
          f"{summary['cached_calls']}; all cached calls USD {summary['total_cache_spend_usd']:.6f}")


if __name__ == "__main__":
    main()
