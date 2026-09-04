"""Runtime compatibility hook for BOTTRADE.

Kept intentionally minimal: order identity is assigned by the trading layer
rather than monkey-patching the Alpaca SDK globally.
"""

# Do not monkey-patch alpaca-py here.  Order submission must remain explicit
# and testable in broker.py.
