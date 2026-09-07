# Dashboard and data quality audit

All validation uses PAPER and simulated broker responses. Configuration and the
NVDA concentration formula are unchanged: largest absolute position value divided
by equity, with no 100% cap (the regression fixture gives exactly 103.3%).

## Metrics

- Quantity-zero positions are excluded from the terminal, broker position counts,
  P&L position summaries and execution exposure calculations. Fractional positions
  and shorts remain included.
- Gross exposure sums absolute position market values. Net exposure remains signed
  and is used for reconciliation against account long/short market values.
- “Max Loss if all stops hit” estimates nonnegative loss from current marks to stop
  prices, weighted by remaining stop quantity. It includes long and short positions,
  nested stop legs, deduplication and quantity caps. Missing/partial protection,
  unconfirmed orders, missing marks or a potentially truncated open-order response
  makes the total unavailable; covered loss remains in the API. It is not a guaranteed
  maximum: gaps/slippage and unfilled stop-limit orders can cause greater losses.
- Fills, buy/sell counts and orders with fills use the same latest 50 FILL activity
  records. Distinct activity IDs prevent duplicates; distinct order IDs count orders.
  An unavailable activity endpoint is reported as unknown, not zero executions.
- Historical long BUY-to-SELL FIFO analysis counts executed stops/OCO legs and
  canceled orders with partial fills. Nested orders and duplicate cumulative
  snapshots are deduplicated. This order-average reconstruction is not a per-fill
  ledger, cannot infer inventory before the supplied history, and does not reconstruct
  short round trips. Terminal FILL activity remains the broker execution record.

Alpaca references: [account activities](https://docs.alpaca.markets/us/docs/account-activities)
and [orders](https://docs.alpaca.markets/us/docs/orders-at-alpaca).

## Volume and persisted observations

Source indicators require a full prior reference window, finite nonnegative volume,
a reference mean greater than 1e-12, and a finite ratio no greater than 1,000,000
(the existing data-quality boundary). Invalid ratios stay missing in indicators
and become null in persisted observations; corrupt values are never clipped into
strong signals. Early signals use the same boundary. Normal ratios are preserved.

The cleaner repairs nested scanner metrics too. It preserves valid records, valid
fields and malformed raw lines. Every changed file gets an exact uniquely named
backup before atomic replacement. A malformed line requires manual recovery and
is deliberately not silently discarded. Cleanup is idempotent.

`pattern_observations.jsonl` is ignored and absent from the repository. On
2026-09-07 the actual Railway PAPER worker was paused for a consistent snapshot.
All 62,618 observations, bot_state.json and 300 analyst-memory records were
backed up, downloaded, checksum-verified and restored to the 500 MB volume at
`/data`. The cleaner found zero invalid fields; both passes changed zero fields,
and all three restored files matched their original SHA-256 checksums exactly.
No historical records were deleted. The migration archive is retained locally
and under `/data/backups/` (SHA-256
`cf8705ac2991aafb45137e60c056a8f6a89b97b73dfffa3e5cc8364fa9fdcc3e`).

The Railway worker uses `python persistent_worker_entrypoint.py` from
`fix/dashboard-data-quality-audit`. This entrypoint requires PAPER and waits for
`/data/.bottrade-restored` before running the worker with `/data` as its working
directory. Create that marker only after a verified restore. Future restarts reuse
the persistent state. For manual cleanup, stop the writer before invoking the
cleaner; its worker-startup invocation runs before the writer starts.

Worker release `f387853c3a1e6b20ba49a83537458e344fc3c079` was verified running
from `/data` with `ALPACA_PAPER=TRUE`; the first post-migration check found 80 new
observations and zero invalid fields across the complete dataset. The separate
web service remains on `app-v1` (release
`f27d5d6729f0fe0ff066709c6ea6e65f394ca42c`) with its existing application entrypoint.
The public terminal reports PAPER, broker/history OK, execution counts from FILL
activity and incomplete stop coverage as unavailable. Nonzero crypto residuals
are displayed in scientific notation rather than rounded to a false quantity zero.

## Validation

Run `ALPACA_PAPER=true python -m pytest -q`,
`ALPACA_PAPER=true python -m unittest discover -s . -p 'test_*.py' -v`,
and `python -m compileall -q .`. CI now includes pytest, because unittest discovery
was skipping module-level regression tests, and runs on the audit branch too.

The baseline also had four failing tests: two older execution-quality assertions
conflicted with the current adaptive sizing contract; two walk-forward tests used
custom signals but were blocked by the unrelated default EMA warm-up requirement.
The simulation now applies that requirement only to its default strategy. The
20-bar fixture contains three complete rolling windows, which its test now asserts.

Local worker validation: 118 pytest tests plus 6 subtests; 104 unittest tests.
Web branch validation: 69 pytest tests; 55 unittest tests. Both release CI runs
passed. Compilation and whitespace checks passed.
