"""Run the multi-agent research lab of protocol section 08: the planted-signal test first (decisions S33-8, S33-12), then
at most ~40 In-Sample candidates behind the vault (S33-5 to S33-9). Every LLM call is cached under agent_lab/cache/ and
--replay reproduces a run offline with no API key.

Planted-signal test (--planted): a synthetic market with one planted effect (src/agents/planted.py) is built into
outputs/agent_lab/planted_data/ (git-ignored, regenerated deterministically); its base rung is chosen by Amendment 7 C1;
6 LLM candidates run, then the planted spec and 4 noise specs are injected at the Validator. PASS: the planted feature
survives, and every candidate whose asset part has |corr| < 0.5 with the planted one is rejected. Whether the LLM agents
proposed the planted feature (or one with |corr| >= 0.9 to it) unaided is reported as information only.

Inputs:  synthetic market (planted test); data/processed/ and data/raw/fred through src/vault.py (In-Sample run)
Outputs: agent_lab/cache/<run>.jsonl, agent_lab/planted/ (candidates.jsonl, trial_log.csv, summary.json,
         vault_server_log.jsonl); the In-Sample run writes docs/trial_log.csv rows (kind "agent")
"""

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from src.agents import planted
from src.agents.graph import Lab
from src.agents.llm import CACHE_DIR, LLM, LLMCache
from src.agents.vault_server import VaultServer, load_script
from src.config import ROOT
from src.vault import Vault

PLANTED_LLM_CANDIDATES = 6  # S33-8
PLANTED_RUN = "planted"
PASS_CORR = 0.5  # S33-8: candidates with |corr| < 0.5 to the planted feature must be rejected
UNAIDED_CORR = 0.9  # S33-8: information only
BASE_RUNGS = ("M1", "M2", "M3")


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
                       and (correlations.get(r["candidate"]) is None or correlations[r["candidate"]] < PASS_CORR)]
    unaided = [r["candidate"] for r in records if r["source"] == "llm" and correlations.get(r["candidate"]) is not None
               and correlations[r["candidate"]] >= UNAIDED_CORR]
    return {"pass": bool(planted_ok and not noise_survivors), "planted_survived": planted_ok,
            "noise_survivors": noise_survivors, "unaided_discovery": bool(unaided), "unaided_candidates": unaided}


def counts(records: list[dict]) -> dict:
    validated = [r for r in records if r.get("passed_validator")]
    vetoed = [r for r in validated if not r["survived"]]
    return {"proposed": len(records), "validated": len(validated), "vetoed": len(vetoed),
            "surviving": sum(r["survived"] for r in records)}


def run_planted(*, mode: str, run_dir: Path, data_root: Path, cache_dir: Path = CACHE_DIR) -> dict:
    """The planted-signal test (S33-8, S33-12); writes run_dir/{candidates.jsonl, trial_log.csv, summary.json,
    vault_server_log.jsonl} and returns the summary. The trial log and server log start empty."""
    cfg = planted.planted_cfg()
    run_dir = Path(run_dir)
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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--planted", action="store_true", help="run the planted-signal test (S33-8)")
    parser.add_argument("--replay", action="store_true", help="answer every LLM call from agent_lab/cache (no key)")
    parser.add_argument("--out", type=Path, default=None, help="run folder (default agent_lab/planted)")
    args = parser.parse_args(argv)
    if not args.planted:
        raise SystemExit("only --planted is available until the In-Sample run is approved (S33-1)")
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
