"""Fixed research candidates. No production activation or parameter fitting."""
import math


def entry_allowed(current, previous, candidate):
    if candidate == 'baseline':
        return True
    if candidate not in {'trend_confirmation', 'trend_not_extended'}:
        raise ValueError('Unknown candidate')
    keys = ('close', 'ema_tendencia', 'ema_rapida', 'ema_lenta', 'atr', 'rsi')
    try:
        values = {k: float(current[k]) for k in keys}
        prior = float(previous['ema_tendencia'])
        if not all(math.isfinite(x) for x in [*values.values(), prior]):
            return False
        trend = (values['close'] > values['ema_tendencia'] and
                 values['ema_rapida'] > values['ema_lenta'] and
                 values['ema_tendencia'] > prior)
        if candidate == 'trend_confirmation':
            return trend
        return (trend and values['atr'] > 0 and values['rsi'] <= 68 and
                values['close'] - values['ema_rapida'] <= 2 * values['atr'])
    except (KeyError, TypeError, ValueError):
        return False
