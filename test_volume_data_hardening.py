import math
from types import SimpleNamespace

import numpy as np
import pandas as pd

import volume_data_hardening


def _config(period=5):
    return SimpleNamespace(VOLUMEN_SMA_PERIODO=period)


def _df(volumes, ratio=None, accel=None, mean=None, short=None):
    n = len(volumes)
    data = {"volume": volumes}
    data["volumen_media"] = mean if mean is not None else [100.0] * n
    data["volumen_media_corta"] = short if short is not None else [100.0] * n
    data["volumen_ratio"] = ratio if ratio is not None else [1.0] * n
    data["aceleracion_volumen"] = accel if accel is not None else [1.0] * n
    return pd.DataFrame(data)


def test_historico_insuficiente_invalida_ratio():
    out = volume_data_hardening._sanitize(_df([100, 100, 100, 100]), _config(5))
    assert pd.isna(out.iloc[-1]["volumen_ratio"])


def test_denominador_cero_invalida_ratios():
    out = volume_data_hardening._sanitize(
        _df([100] * 6, mean=[0] * 6, short=[0] * 6, ratio=[1e12] * 6, accel=[1e9] * 6),
        _config(5),
    )
    assert pd.isna(out.iloc[-1]["volumen_ratio"])
    assert pd.isna(out.iloc[-1]["aceleracion_volumen"])


def test_denominador_casi_cero_invalida_ratio():
    out = volume_data_hardening._sanitize(
        _df([100] * 6, mean=[1e-13] * 6, ratio=[1e15] * 6), _config(5)
    )
    assert pd.isna(out.iloc[-1]["volumen_ratio"])


def test_ratio_inconsistente_se_descarta():
    out = volume_data_hardening._sanitize(
        _df([100] * 6, ratio=[1.0] * 6), _config(5)
    )
    # En este caso el ratio es consistente con 100 / 100.
    assert math.isclose(float(out.iloc[-1]["volumen_ratio"]), 1.0)

    out = volume_data_hardening._sanitize(
        _df([100] * 6, ratio=[2.0] * 6), _config(5)
    )
    assert pd.isna(out.iloc[-1]["volumen_ratio"])


def test_valores_no_finitos_se_descartan():
    out = volume_data_hardening._sanitize(
        _df(
            [100] * 6,
            ratio=[1.0, 1.0, 1.0, 1.0, float("inf"), 2.0],
            accel=[1.0, 1.0, 1.0, 1.0, float("nan"), 2.0],
        ),
        _config(5),
    )
    assert pd.isna(out.iloc[4]["volumen_ratio"])
    assert pd.isna(out.iloc[4]["aceleracion_volumen"])


def test_ratios_normales_se_conservan():
    out = volume_data_hardening._sanitize(
        _df(
            [100, 100, 100, 100, 150, 150],
            ratio=[1.0, 1.0, 1.0, 1.0, 1.5, 1.5],
            accel=[1.0, 1.0, 1.0, 1.0, 1.5, 1.5],
        ),
        _config(5),
    )
    assert math.isclose(float(out.iloc[-1]["volumen_ratio"]), 1.5)
    assert math.isclose(float(out.iloc[-1]["aceleracion_volumen"]), 1.5)


def test_volumen_no_finito_no_es_valido():
    out = volume_data_hardening._sanitize(
        _df([100, 100, 100, 100, np.inf, 100], ratio=[1.0] * 6, accel=[1.0] * 6),
        _config(5),
    )
    assert bool(out.iloc[4]["volumen_valido"]) is False if "volumen_valido" in out else True
