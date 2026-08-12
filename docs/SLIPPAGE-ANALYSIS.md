# Slippage Analysis

Buy slippage per unit is `VWAP - reference`; sell slippage is `reference - VWAP`. Amount multiplies by filled quantity and bps divides per-unit slippage by the frozen reference price. Positive values are adverse. Multi-fill orders use the stored average fill price (VWAP).
