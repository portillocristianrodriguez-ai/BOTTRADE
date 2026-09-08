"""User-requested PAPER-only adjustment of the existing NVDA OCO, 2026-09-08.

Replace only its limit price, once. Never submit/cancel an order or modify
strategy parameters. Orders created after the request are ineligible.
"""
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import time


BASE_URL = 'https://paper-api.alpaca.markets'
SERVICE_ID = '47e920a7-30c0-4095-8d36-0a1fa23dc696'
ENVIRONMENT_ID = '9987137c-0faf-43d2-81c6-0a48076563d8'
REQUESTED_AT = datetime.fromisoformat('2026-09-08T11:13:19+00:00')
EXPIRES_AT = datetime.fromisoformat('2026-09-08T13:00:00+00:00')
TARGET = Decimal('231.75')
MARKER = '.nvda-tp-23175-20260908.json'
ACTIVE = {'new', 'accepted', 'held', 'accepted_for_bidding'}


def report(message):
    print('[NVDA-TP-ONCE] ' + message, flush=True)


def number(value):
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError('Non-finite broker value')
    return result


def created_before_request(order):
    created = datetime.fromisoformat(order['created_at'].replace('Z', '+00:00'))
    return created.tzinfo is not None and created < REQUESTED_AT


def validate(position, orders):
    """Require one pre-existing, unfilled OCO covering the entire long position."""
    if position.get('symbol') != 'NVDA' or position.get('side') != 'long':
        raise ValueError('No existing long NVDA position')
    qty = number(position['qty'])
    if qty <= 0 or len(orders) != 1:
        raise ValueError('Ambiguous NVDA quantity or open orders')
    tp = orders[0]
    if (tp.get('symbol') != 'NVDA' or tp.get('side') != 'sell'
            or tp.get('type') != 'limit' or tp.get('order_class') != 'oco'
            or tp.get('status') not in ACTIVE or not created_before_request(tp)
            or number(tp['filled_qty']) != 0 or number(tp['qty']) != qty
            or tp.get('replaced_by') or not tp.get('id')):
        raise ValueError('Existing NVDA take profit is not eligible')
    legs = tp.get('legs') or []
    if len(legs) != 1:
        raise ValueError('Expected one linked stop loss')
    stop = legs[0]
    if (stop.get('symbol') != 'NVDA' or stop.get('side') != 'sell'
            or stop.get('type') not in {'stop', 'stop_limit'}
            or stop.get('status') not in ACTIVE or not created_before_request(stop)
            or number(stop['filled_qty']) != 0 or number(stop['qty']) != qty
            or not stop.get('id') or stop.get('replaced_by')
            or not 0 < number(stop['stop_price']) < TARGET):
        raise ValueError('Linked stop loss is not eligible')
    if number(tp['limit_price']) <= 0:
        raise ValueError('Invalid take profit price')
    return tp, stop


def write_marker(path, payload, exclusive=False):
    # Durable claim precedes PATCH: an uncertain response is never retried.
    with path.open('x' if exclusive else 'w') as handle:
        json.dump(payload, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    fd = os.open(str(path.parent), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def apply_once(directory, session=None, now=None, wait=time.sleep):
    env = os.environ
    if (env.get('RAILWAY_SERVICE_ID') != SERVICE_ID
            or env.get('RAILWAY_ENVIRONMENT_ID') != ENVIRONMENT_ID
            or env.get('ALPACA_PAPER', '').strip().lower()
            not in {'true', '1', 'yes', 'si', 'sí', 'on'}):
        report('SKIPPED: requires the authorized BOTTRADE PAPER service')
        return
    path = Path(directory) / MARKER
    if path.exists():
        report('SKIPPED: one-time request already recorded; no order changes')
        return
    now = now or datetime.now(timezone.utc)
    if not REQUESTED_AT <= now < EXPIRES_AT:
        report('EXPIRED: no order changes')
        return
    record = {'status': 'preflight', 'target': str(TARGET)}
    claimed = False
    try:
        key, secret = env.get('ALPACA_API_KEY'), env.get('ALPACA_API_SECRET')
        if not key or not secret:
            raise ValueError('Missing PAPER credentials')
        if session is None:
            import requests
            session = requests.Session()
        headers = {'APCA-API-KEY-ID': key, 'APCA-API-SECRET-KEY': secret}

        def request(method, route, **kwargs):
            response = session.request(method, BASE_URL + route, headers=headers,
                                       timeout=15, allow_redirects=False, **kwargs)
            if not 200 <= response.status_code < 300:
                # Do not print response bodies or credentials into runtime logs.
                raise RuntimeError('Alpaca HTTP ' + str(response.status_code))
            return response.json()

        position = request('GET', '/v2/positions/NVDA')
        orders = request('GET', '/v2/orders', params={
            'symbols': 'NVDA', 'status': 'open', 'nested': 'true', 'limit': 500})
        report('PREFLIGHT: NVDA qty=' + str(position.get('qty'))
               + '; open order groups=' + str(len(orders)))
        tp, stop = validate(position, orders)
        # Re-read the same order ID and position just before the durable claim.
        current = request('GET', '/v2/orders/' + tp['id'], params={'nested': 'true'})
        position = request('GET', '/v2/positions/NVDA')
        current, current_stop = validate(position, [current])
        if (current['id'] != tp['id'] or current_stop['id'] != stop['id']
                or current['qty'] != tp['qty']
                or current_stop['stop_price'] != stop['stop_price']
                or current['limit_price'] != tp['limit_price']):
            raise ValueError('NVDA protection changed during preflight')
        record.update(status='claimed', order_id=tp['id'], stop_id=stop['id'],
                      qty=tp['qty'], old_limit=tp['limit_price'],
                      stop_price=stop['stop_price'])
        write_marker(path, record, exclusive=True)
        claimed = True
        if number(tp['limit_price']) == TARGET:
            record['status'] = 'already_at_target'
        else:
            report('REQUEST: PAPER NVDA qty=' + str(tp['qty']) + ' TP='
                   + str(tp['limit_price']) + ' -> 231.75; SL='
                   + str(stop['stop_price']) + '; order=' + tp['id'])
            replacement = request('PATCH', '/v2/orders/' + tp['id'],
                                  json={'limit_price': str(TARGET)})
            record['replacement_id'] = replacement['id']
            write_marker(path, record)
            verified = False
            for attempt in range(6):
                updated = request('GET', '/v2/orders/' + replacement['id'])
                if (updated.get('symbol') != 'NVDA' or updated.get('side') != 'sell'
                        or updated.get('type') != 'limit'
                        or number(updated['limit_price']) != TARGET
                        or number(updated['qty']) != number(tp['qty'])
                        or updated.get('time_in_force') != tp.get('time_in_force')
                        or updated.get('replaces') != tp['id']):
                    raise ValueError('Replacement verification mismatch')
                if updated.get('status') in ACTIVE:
                    sl = request('GET', '/v2/orders/' + stop['id'])
                    if (sl.get('status') not in ACTIVE or sl.get('symbol') != 'NVDA'
                            or sl.get('side') != 'sell'
                            or number(sl['stop_price']) != number(stop['stop_price'])
                            or number(sl['qty']) != number(stop['qty'])):
                        raise ValueError('Stop loss verification requires review')
                    verified = True
                    break
                if attempt < 5:
                    wait(2)
            if not verified:
                raise ValueError('Replacement acceptance not yet confirmed')
            record['status'] = 'verified'
        write_marker(path, record)
        report('VERIFIED: PAPER NVDA qty=' + str(tp['qty'])
               + ' TP=231.75; SL=' + str(stop['stop_price'])
               + '; future entries retain standard strategy')
    except FileExistsError:
        report('SKIPPED: another process already claimed this one-time request')
    except Exception as exc:
        if claimed:
            record['status'] = 'needs_review'
            try:
                write_marker(path, record)
            except OSError:
                pass
        reason = str(exc) if type(exc) in {ValueError, RuntimeError} else type(exc).__name__
        report('NOT VERIFIED: ' + reason
               + '; no retry, cancellation, or new order will be attempted')


if __name__ == '__main__':
    apply_once(os.environ.get('BOTTRADE_DATA_DIR', '/data'))
