# Agent lab: In-Sample review

Base rung M2 (S33-10; In-Sample headline net Sharpe -0.986). Proposed 40, invalid 24, refused 0, validated 0, vetoed 0, surviving 0. LLM spend of the run: USD 0.127144 over 80 cached calls.

A surviving candidate passed the Validator (leakage, warm-up, redundancy, the §07 gate against the base rung on the same weeks) and neither the Skeptic nor Risk (tool checks, then LLM) vetoed it. No candidate enters M5 until Eliya and Mattia approve it by name (Session 3.3 step 7).

## Surviving candidates

None.

## Every candidate

| # | Name | Stage | Uplift | P | Skeptic veto | Risk veto | Survived |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | XS_RELSTRENGTH_13W | walk_forward | 0.039 | 0.611 |  |  | False |
| 2 | vol_of_vol_mktvar | walk_forward | -0.150 | 0.212 |  |  | False |
| 3 | mktvar_conditional_short_reversal | redundancy | n/a | n/a |  |  | False |
| 4 | rel_mom_26_4_credit | walk_forward | 0.146 | 0.755 |  |  | False |
| 5 | neg_resid_overshoot_volscaled_cs_z | invalid_spec | n/a | n/a |  |  | False |
| 6 | beta_adj_resid_rev_3w_z52 | invalid_spec | n/a | n/a |  |  | False |
| 7 | beta_adj_residual_momentum_26w_cs_z | redundancy | n/a | n/a |  |  | False |
| 8 | mktvar_conditional_short_reversal | invalid_spec | n/a | n/a |  |  | False |
| 9 | rev_3w_rel_volscaled_cs_z | invalid_spec | n/a | n/a |  |  | False |
| 10 | idiosyncratic_residual_reversal_3w_volscaled | walk_forward | 0.090 | 0.816 |  |  | False |
| 11 | cs_z_r2_minus_asymmetry | invalid_spec | n/a | n/a |  |  | False |
| 12 | downside_upside_semivariance_ratio_26w | invalid_spec | n/a | n/a |  |  | False |
| 13 | autocorr_rel_ret_26_cs_z_bear | invalid_spec | n/a | n/a |  |  | False |
| 14 | (invalid) | invalid_spec | n/a | n/a |  |  | False |
| 15 | lag_beta_market_catchup_cs_z_vix | redundancy | n/a | n/a |  |  | False |
| 16 | downside_beta_asymmetry_52w_cs_z_mktvar | invalid_spec | n/a | n/a |  |  | False |
| 17 | (invalid) | invalid_spec | n/a | n/a |  |  | False |
| 18 | downside_beta_asymmetry_mktvar | invalid_spec | n/a | n/a |  |  | False |
| 19 | downside_beta_asymmetry_52w | invalid_spec | n/a | n/a |  |  | False |
| 20 | downside_capture_resilience_52w_cs_z | invalid_spec | n/a | n/a |  |  | False |
| 21 | neg_beta_in_bear | invalid_spec | n/a | n/a |  |  | False |
| 22 | mktvar_downside_beta_gap_cs_z | walk_forward | 0.126 | 0.857 |  |  | False |
| 23 | beta_decoupling_catchup_13w_mktvar | invalid_spec | n/a | n/a |  |  | False |
| 24 | (invalid) | invalid_spec | n/a | n/a |  |  | False |
| 25 | rel_path_efficiency_13w_cs_z | invalid_spec | n/a | n/a |  |  | False |
| 26 | cs_inv_resid_dispersion_4w_mktvar | invalid_spec | n/a | n/a |  |  | False |
| 27 | vix_scaled_beta_residual_13w | invalid_spec | n/a | n/a |  |  | False |
| 28 | Down_Up_RelRet_Asymmetry_x_MktVar | invalid_spec | n/a | n/a |  |  | False |
| 29 | beta_divergence_reversal_4w_mktvar | walk_forward | 0.072 | 0.648 |  |  | False |
| 30 | RECOVERY_LAG_13W_MKTVAR | redundancy | n/a | n/a |  |  | False |
| 31 | beta_implied_gap_13w_mktvar_scaled | walk_forward | -0.055 | 0.422 |  |  | False |
| 32 | cs_z_credit_gated_trend_gap_26w | walk_forward | -0.124 | 0.268 |  |  | False |
| 33 | MOM26_tstat_cs_z_mulstate_MKTVAR | walk_forward | 0.133 | 0.857 |  |  | False |
| 34 | resid_vol_compression_ratio_13_52 | walk_forward | -0.121 | 0.155 |  |  | False |
| 35 | relret_lag2_autocorr_13w | invalid_spec | n/a | n/a |  |  | False |
| 36 | rel_trend_reversion_cs_z_gated_mkt_var | invalid_spec | n/a | n/a |  |  | False |
| 37 | beta_gap_26_52_mktvar | walk_forward | -0.059 | 0.373 |  |  | False |
| 38 | (invalid) | invalid_spec | n/a | n/a |  |  | False |
| 39 | down_market_capture_asymmetry_cs_z_x_mkt_var | walk_forward | -0.176 | 0.205 |  |  | False |
| 40 | pead_path_efficiency_8w_mktvar | invalid_spec | n/a | n/a |  |  | False |

## Recognition probe (S33-17)

Hit rate 3/9 (0.33; chance 0.11): a measured residual of the anonymisation, which changes nothing in the run.

| Code | Answer | Hit |
| --- | --- | --- |
| A1 | XLE | False |
| A2 | XLE | False |
| A3 | XLU | False |
| A4 | XLE | False |
| A5 | XLK | True |
| A6 | XLU | True |
| A7 | XLE | True |
| A8 | XLU | False |
| A9 | XLE | False |
