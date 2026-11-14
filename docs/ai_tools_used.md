# AI tools used

Where AI is used in this project and for what. Reviewed and completed by hand by the team (operating manual §3.1). Every
member can explain every part of the code and the methodology, as the course instructions require.

## 1. AI inside the research: the multi-agent feature lab

The lab (pre-registration §08) lets language-model agents propose new predictive features for the model ladder. The agents
never trade and never see Out-of-Sample data: they reach the data only through an MCP vault server that serves anonymised
In-Sample summaries (sectors coded A1 to A9) and refuses any date after 27 December 2019. Every proposal is a row of
`docs/trial_log.csv`, so it counts in the deflated Sharpe ratio, and every model call is cached under `agent_lab/`, so the
whole lab replays offline at zero cost.

| Agent | Kind | What it does |
| --- | --- | --- |
| Hypothesis | Language model | Proposes an economic idea for a new feature from the anonymised summaries and the trial history |
| Coder | Language model | Writes the idea as an expression of the feature language (DSL); in round 2 it gets one repair attempt when the Validator rejects it |
| Validator | Deterministic code | Checks leakage (no future data), warm-up, redundancy with existing features, and runs the walk-forward test of the base model plus the feature |
| Skeptic | Language model | Reviews the surviving feature and can veto it with a stated reason |
| Risk | Deterministic checks plus a language model | Tool checks on turnover, residual beta and adverse-cost uplift; a model veto counts only for a named concern that does not rest on Sharpe or costs |
| Human gate | Eliya Allam and Mattia Cervelli | A feature enters the model only if both approve it by name |

Two safety tests guard the lab. The **planted-signal test** builds a synthetic market with one known signal: the lab must
keep that signal and reject noise before it may touch real data. The **recognition probe** asks the model to name each
anonymised sector, measuring how much it recognises from its pre-training (pretrained-model leakage).

| Round | Model | Base model | Calls and spend | Outcome |
| --- | --- | --- | --- | --- |
| Round 1 (3–5 Nov 2026) | DeepSeek V4.1 Flash (`deepseek-flash`; S33-1) | M2 | Planted test passed on attempt 4; 40 In-Sample proposals (80 calls); USD 0.16 in total | 24 invalid, 4 redundant, 12 failed, 0 survived: M5 absent (S33-19). Probe: 3 of 9 sectors recognised (33%, against 11% by chance), disclosed as a measured residual (S33-18) |
| Round 2 (6–9 Nov 2026) | `claude-fable-5-1` at medium effort, the most capable Claude model available on the API at run time (S43-1) | M7 | 3 calibration calls and the planted-signal test (attempt 5); USD 1.39 of the USD 10 budget | Planted test failed: the planted feature passed the Validator and the Skeptic, but Risk's turnover check vetoed it against slow M7. The rule was not changed after the fact, so no real data was read and M9 is absent (S43-7, S43-9) |

## 2. AI and optimisation in the trading models

| Model | Technique | Optimised parameter and how |
| --- | --- | --- |
| M1, M2, M6, M7 | Ridge regression (M2, M6, M7 with five pre-registered regime interactions; M6, M7 on a 4-week target; M7 with score smoothing) | λ ∈ {0.1, 1, 10} and, for M7, the smoothing half-life ∈ {2, 4} weeks, chosen at every quarterly refit on the last 104 training weeks |
| M3 | Gradient-boosted trees (LightGBM, deterministic) | Tree depth ∈ {2, 3}, chosen the same way |
| M8 | Learning to rank (LightGBM LambdaRank) on the 4-week target, with smoothing | Depth ∈ {2, 3} × half-life ∈ {2, 4} |
| ENS | Equal-weight ensemble of the ranks of M1, M2 and M3 | None |
| M0\* | Walk-forward optimisation of the momentum lookback | Lookback ∈ {13, 26, 52} weeks, chosen at every refit |

## 3. AI assistants

| Tool | Used for |
| --- | --- |
| AI coding assistants (Claude, Codex) | Support with writing and testing code and with drafting documentation |

All assistant output was reviewed by a team member before it was committed, and every commit and review was made by a team
member under their own name.
