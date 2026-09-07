"""Strict, shared OHLCV validation for reproducible simulations."""
import numpy as np
import pandas as pd


def clean_ohlcv(df):
    required = ['open', 'high', 'low', 'close', 'volume']
    if not isinstance(df, pd.DataFrame) or not set(required).issubset(df.columns):
        raise ValueError('Missing OHLCV columns')
    out = df.copy()
    out.index = pd.to_datetime(out.index, utc=True)
    if out.index.hasnans or out.index.has_duplicates:
        raise ValueError('Missing or duplicate bar timestamps')
    out = out.sort_index()
    values = out[required].apply(pd.to_numeric, errors='coerce')
    if not np.isfinite(values.to_numpy()).all():
        raise ValueError('OHLCV contains missing or non-finite values')
    if (values[['open','high','low','close']] <= 0).any().any() or (values.volume < 0).any():
        raise ValueError('Invalid price or volume')
    if ((values.high < values[['open','close','low']].max(axis=1)) |
        (values.low > values[['open','close','high']].min(axis=1))).any():
        raise ValueError('Inconsistent OHLC bounds')
    out[required] = values
    return out
