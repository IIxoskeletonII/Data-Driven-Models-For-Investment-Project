"""Model-input pipeline and M0 of src/models.py (§06, §07; Amendment 2 C1 and C7; Amendment 3 C8; S22-6, S22-11).

The winsorising level is passed explicitly in cfg (features.winsor_quantiles = [0.01, 0.99], Amendment 3 C8), since the
key is added to config.yaml in a separate pull request. Expected parameters are computed here with numpy.nanquantile
(linear interpolation) and the mean and ddof=1 standard deviation over the distinct training weeks.
"""

import copy

import numpy as np
import pandas as pd
import pytest

from src import contracts, models
from src.config import load_config

BASE_CFG = load_config()
CFG = copy.deepcopy(BASE_CFG)
CFG["features"]["winsor_quantiles"] = [0.01, 0.99]
QUANTILES = (0.01, 0.99)
SECTORS = list(contracts.universe(CFG).sectors)
ASSET = list(CFG["features"]["asset"])
STATES = list(CFG["features"]["states"])
CONTINUOUS = ["MKT_VAR", "VIX", "TERM", "CREDIT"]
SCALED_COLUMNS = ["BEAR24", "MKT_VAR", "VIX_Z", "TERM", "CREDIT"]
INTERACTIONS = contracts.interaction_columns(CFG)
DAY = pd.Timedelta(days=1)

TRAIN_FRIDAYS = pd.date_range("2010-01-08", periods=30, freq="7D")
TEST_FRIDAYS = pd.date_range(TRAIN_FRIDAYS[-1] + 7 * DAY, periods=6, freq="7D")


def weekly(fridays: pd.DatetimeIndex) -> pd.MultiIndex:
    return pd.MultiIndex.from_arrays([fridays - 4 * DAY, fridays], names=["date_open", "date_close"])


def make_states(seed: int = 0) -> pd.DataFrame:
    """Weekly market states (contract 4) on the 30 training and 6 test weeks; BEAR24 is 1 in a few weeks."""
    fridays = TRAIN_FRIDAYS.append(TEST_FRIDAYS)
    rng = np.random.default_rng(seed)
    n = len(fridays)
    bear = np.zeros(n)
    bear[[3, 4, 5, 17, 18, 31, 32]] = 1.0
    states = pd.DataFrame({
        "BEAR24": bear,
        "MKT_VAR": rng.lognormal(np.log(1e-4), 0.8, n),
        "VIX": rng.lognormal(np.log(18.0), 0.4, n),
        "TERM": rng.normal(1.5, 1.0, n),
        "CREDIT": rng.lognormal(np.log(2.5), 0.3, n),
    }, index=weekly(fridays))[STATES]
    contracts.validate_market_states(states)
    return states


def make_features(fridays: pd.DatetimeIndex, seed: int = 1) -> pd.DataFrame:
    index = pd.MultiIndex.from_product([fridays, SECTORS], names=["date_close", "ticker"])
    rng = np.random.default_rng(seed)
    return pd.DataFrame(rng.normal(size=(len(index), len(ASSET))), index=index, columns=ASSET)


def hand_params(states: pd.DataFrame) -> dict[str, dict[str, float]]:
    """1/99 winsorising bounds, then mean and ddof=1 std of the clipped values, NaN ignored, one value per week."""
    out = {"lower": {}, "upper": {}, "mean": {}, "std": {}}
    for column in CONTINUOUS:
        x = states[column].to_numpy(dtype=np.float64)
        lo, hi = np.nanquantile(x, QUANTILES)
        clipped = np.clip(x, lo, hi)
        out["lower"][column], out["upper"][column] = lo, hi
        out["mean"][column] = np.nanmean(clipped)
        out["std"][column] = np.nanstd(clipped, ddof=1)
    return out


def hand_scaled(states: pd.DataFrame, params: dict) -> pd.DataFrame:
    scaled = pd.DataFrame(index=states.index)
    scaled["BEAR24"] = states["BEAR24"]
    for column in CONTINUOUS:
        clipped = np.clip(states[column].to_numpy(), params["lower"][column], params["upper"][column])
        name = "VIX_Z" if column == "VIX" else column
        scaled[name] = (clipped - params["mean"][column]) / params["std"][column]
    return scaled


def hand_design(features: pd.DataFrame, states: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Six asset columns plus the five interactions: asset × raw BEAR24 × scaled MKT_VAR / VIX_Z."""
    scaled = hand_scaled(states, params).droplevel("date_open")
    week = scaled.loc[pd.DatetimeIndex(features.index.get_level_values("date_close"))].to_numpy()
    by_name = dict(zip(SCALED_COLUMNS, week.T, strict=True))
    design = features[ASSET].copy()
    for terms, name in zip(CFG["features"]["interactions"], INTERACTIONS, strict=True):
        product = features[terms[0]].to_numpy().copy()
        for term in terms[1:]:
            product = product * by_name[term]
        design[name] = product
    return design


def train_states(states: pd.DataFrame) -> pd.DataFrame:
    return states[pd.DatetimeIndex(states.index.get_level_values("date_close")).isin(TRAIN_FRIDAYS)]


def assert_params_close(actual: dict, expected: dict) -> None:
    for key in ("lower", "upper", "mean", "std"):
        for column in CONTINUOUS:
            assert actual[key][column] == pytest.approx(expected[key][column], rel=1e-12, abs=1e-15), (key, column)


# ---------------------------------------------------------------- state scaling


def test_fit_state_scaling_hand_values_with_a_missing_week():
    states = train_states(make_states())
    states.iloc[7, STATES.index("VIX")] = np.nan  # NaN ignored
    params = models.fit_state_scaling(states, cfg=CFG)
    assert_params_close(params, hand_params(states))
    for key in ("lower", "upper", "mean", "std"):
        assert "BEAR24" not in params[key]  # Amendment 2 C1: no parameters for the indicator
    lo, hi = params["lower"]["MKT_VAR"], params["upper"]["MKT_VAR"]
    x = states["MKT_VAR"].to_numpy()
    assert x.min() < lo < hi < x.max()  # the 1/99 clip binds on 30 weeks


def test_scale_states_hand_values_and_bear24_untouched():
    states = make_states()
    params = models.fit_state_scaling(train_states(states), cfg=CFG)
    scaled = models.scale_states(states, params)
    assert list(scaled.columns) == SCALED_COLUMNS
    assert scaled.index.equals(states.index)
    assert np.array_equal(scaled["BEAR24"].to_numpy(), states["BEAR24"].to_numpy())
    expected = hand_scaled(states, hand_params(train_states(states)))
    np.testing.assert_allclose(scaled[SCALED_COLUMNS].to_numpy(), expected[SCALED_COLUMNS].to_numpy(), rtol=1e-12, atol=1e-12)


def test_scale_states_zero_dispersion_gives_zero():
    states = make_states()
    states["TERM"] = 1.25
    params = models.fit_state_scaling(train_states(states), cfg=CFG)
    scaled = models.scale_states(states, params)
    assert np.array_equal(scaled["TERM"].to_numpy(), np.zeros(len(states)))


def test_missing_winsor_quantiles_key_raises_key_error():
    cfg = copy.deepcopy(CFG)
    del cfg["features"]["winsor_quantiles"]
    states = make_states()
    with pytest.raises(KeyError) as excinfo:
        models.fit_state_scaling(train_states(states), cfg=cfg)
    message = str(excinfo.value)
    assert "winsor_quantiles" in message and "Amendment 3" in message
    with pytest.raises(KeyError):
        models.fit_transform_train(make_features(TRAIN_FRIDAYS), states, cfg=cfg)


# ---------------------------------------------------------------- design matrix


def test_fit_transform_train_fits_on_distinct_training_weeks_only():
    states = make_states()
    train = make_features(TRAIN_FRIDAYS)
    _, params = models.fit_transform_train(train, states, cfg=CFG)
    expected = hand_params(train_states(states))
    assert_params_close(params, expected)
    # weighting each week by its 9 panel rows would give a different ddof=1 std: the test separates the two
    panel = np.repeat(np.clip(train_states(states)["VIX"].to_numpy(), expected["lower"]["VIX"], expected["upper"]["VIX"]), 9)
    assert abs(np.std(panel, ddof=1) - expected["std"]["VIX"]) > 1e-6


def test_params_ignore_test_weeks_and_test_rows():
    states = make_states()
    train = make_features(TRAIN_FRIDAYS)
    x_a, params_a = models.fit_transform_train(train, states, cfg=CFG)
    changed = states.copy()
    test_rows = pd.DatetimeIndex(changed.index.get_level_values("date_close")).isin(TEST_FRIDAYS)
    changed.loc[test_rows, CONTINUOUS] = changed.loc[test_rows, CONTINUOUS].to_numpy() * 50.0
    changed.loc[test_rows, "BEAR24"] = 1.0 - changed.loc[test_rows, "BEAR24"]
    x_b, params_b = models.fit_transform_train(train, changed, cfg=CFG)
    for key in ("lower", "upper", "mean", "std"):
        assert params_a[key] == params_b[key]
    assert np.array_equal(x_a.to_numpy(), x_b.to_numpy())


def test_fit_transform_train_columns_values_and_metadata():
    states = make_states()
    train = make_features(TRAIN_FRIDAYS)
    x, params = models.fit_transform_train(train, states, cfg=CFG)
    assert INTERACTIONS == ["BETA52_x_BEAR24_x_MKT_VAR", "BETA52_x_BEAR24", "MOM26_1_x_BEAR24", "MOM26_1_x_MKT_VAR",
                            "VOL13_x_VIX_Z"]
    assert list(x.columns) == ASSET + INTERACTIONS
    assert x.index.equals(train.index)
    assert all(x[c].dtype == np.float64 for c in x.columns)
    assert params["interactions"] is True
    assert list(params["columns"]) == ASSET + INTERACTIONS
    np.testing.assert_array_equal(x[ASSET].to_numpy(), train[ASSET].to_numpy())
    expected = hand_design(train, states, hand_params(train_states(states)))
    np.testing.assert_allclose(x.to_numpy(), expected[ASSET + INTERACTIONS].to_numpy(), rtol=1e-12, atol=1e-12)


def test_bear24_interactions_are_exactly_zero_when_bear24_is_zero():
    states = make_states()
    train = make_features(TRAIN_FRIDAYS)
    x, _ = models.fit_transform_train(train, states, cfg=CFG)
    bear = states["BEAR24"].droplevel("date_open").loc[pd.DatetimeIndex(train.index.get_level_values("date_close"))]
    calm = bear.to_numpy() == 0.0
    assert calm.any() and (~calm).any()
    for name in ("BETA52_x_BEAR24_x_MKT_VAR", "BETA52_x_BEAR24", "MOM26_1_x_BEAR24"):
        assert (x[name].to_numpy()[calm] == 0.0).all(), name
        assert (x[name].to_numpy()[~calm] != 0.0).all(), name


def test_interactions_false_gives_the_six_asset_columns():
    states = make_states()
    train = make_features(TRAIN_FRIDAYS)
    x, params = models.fit_transform_train(train, states, interactions=False, cfg=CFG)
    assert list(x.columns) == ASSET
    assert params["interactions"] is False
    assert list(params["columns"]) == ASSET
    np.testing.assert_array_equal(x.to_numpy(), train[ASSET].to_numpy())


def test_transform_test_applies_the_stored_training_parameters():
    states = make_states()
    test_rows = pd.DatetimeIndex(states.index.get_level_values("date_close")).isin(TEST_FRIDAYS)
    states.loc[test_rows & (np.arange(len(states)) % 2 == 0), "VIX"] = 1000.0  # beyond the training upper bound
    states.loc[test_rows & (np.arange(len(states)) % 2 == 1), "MKT_VAR"] = 0.0  # below the training lower bound
    train = make_features(TRAIN_FRIDAYS)
    test = make_features(TEST_FRIDAYS, seed=2)
    x_train, params = models.fit_transform_train(train, states, cfg=CFG)
    x_test = models.transform_test(test, states, params)
    expected_params = hand_params(train_states(states))
    expected = hand_design(test, states, expected_params)
    assert list(x_test.columns) == ASSET + INTERACTIONS
    assert x_test.index.equals(test.index)
    np.testing.assert_allclose(x_test.to_numpy(), expected[ASSET + INTERACTIONS].to_numpy(), rtol=1e-12, atol=1e-12)
    vix_z_cap = (expected_params["upper"]["VIX"] - expected_params["mean"]["VIX"]) / expected_params["std"]["VIX"]
    capped = test.index.get_level_values("date_close").isin(TEST_FRIDAYS[::2])
    np.testing.assert_allclose(x_test.loc[capped, "VOL13_x_VIX_Z"].to_numpy(), test.loc[capped, "VOL13"].to_numpy() * vix_z_cap,
                               rtol=1e-12)
    # applying the stored parameters to the training rows reproduces the training design matrix
    np.testing.assert_allclose(models.transform_test(train, states, params).to_numpy(), x_train.to_numpy(), rtol=1e-14,
                               atol=1e-15)


def test_transform_test_without_interactions():
    states = make_states()
    train, test = make_features(TRAIN_FRIDAYS), make_features(TEST_FRIDAYS, seed=2)
    _, params = models.fit_transform_train(train, states, interactions=False, cfg=CFG)
    x_test = models.transform_test(test, states, params)
    assert list(x_test.columns) == ASSET
    np.testing.assert_array_equal(x_test.to_numpy(), test[ASSET].to_numpy())


# ---------------------------------------------------------------- M0


def m0_inputs() -> tuple[pd.DataFrame, pd.Series]:
    x = make_features(TRAIN_FRIDAYS[:5])
    x["MOM13_1"] = np.arange(len(x), dtype=np.float64)
    y = pd.Series(np.random.default_rng(4).normal(size=len(x)), index=x.index, name="y")
    return x, y


def test_m0_fit_is_a_no_op_returning_self():
    x, y = m0_inputs()
    model = models.M0()
    before = copy.deepcopy(vars(model))
    assert model.fit(x, y) is model
    assert vars(model).keys() == before.keys()
    assert all(vars(model)[k] == before[k] for k in before)
    assert model.name == "M0"
    assert isinstance(model, contracts.ScoreModel)


def test_m0_score_is_the_feature_column():
    x, y = m0_inputs()
    model = models.M0().fit(x, y)
    score = model.score(x)
    assert score.name == "score"
    assert score.dtype == np.float64
    assert score.index.equals(x.index)
    assert np.array_equal(score.to_numpy(), x["MOM26_1"].to_numpy())
    variant = models.M0(feature="MOM13_1", name="M0_13").score(x)
    assert np.array_equal(variant.to_numpy(), x["MOM13_1"].to_numpy())
    assert variant.name == "score"
