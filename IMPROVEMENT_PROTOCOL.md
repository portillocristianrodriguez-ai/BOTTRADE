# Predefined improvement protocol — 7 September 2026

The August 17–September 7 benchmark has already been inspected. It must not
be called untouched validation or used to claim a newly discovered edge.

Test two fixed entry filters against the existing signal, preserving every
SELL signal and all simulation exits:

1. Trend confirmation: close above trend EMA, fast EMA above slow EMA, and
   rising trend EMA compared with the preceding bar.
2. The same trend filter, plus RSI <= 68 and close no more than two ATR above
   the fast EMA. These thresholds are fixed before viewing these tests.

Development: June 22–July 20, four non-overlapping weekly windows.
Validation: July 20–August 17, four weekly windows. No retuning after opening
validation. Previous data provide indicator warmup only. These historical
periods are new to this comparison, but not prospective independent evidence
against the original strategy's development.

Six instruments and costs match the preceding audit. Test both baseline and
doubled slippage. Select one candidate on development only. Require positive
mean net return, improvement over baseline in BOTH stocks and crypto and both
cost scenarios, no worse worst-window drawdown, and at least 20 closed trades
per asset class. Require these conditions again on validation. If no candidate
passes, publish the rejection and do not activate either filter. This is a
minimum rejection screen, not a statistical proof of profitability.

Execution correctness fixes can ship independently of strategy selection.
PAPER and the accepted NVDA position/concentration remain unchanged.
