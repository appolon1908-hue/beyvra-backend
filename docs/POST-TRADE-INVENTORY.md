# Post-Trade Inventory

The existing `SimulatedTrade`, `SimulatedPosition`, and `SimulatedReservation` models are simulation-only execution/financial projections. They do not provide canonical allocation, obligation, settlement-instruction, confirmation, correction, exception, or evidence authority. The Financial Service client is an authoritative external boundary and its mutations remain disabled. The new `apps.post_trade` domain owns provider-neutral post-trade records while retaining legacy simulated records as compatibility inputs.

Classification: existing fill capture is PARTIAL/SIMULATION_ONLY; position settlement is SIMULATION_ONLY; reservation handling is AUTHORITATIVE for demo funds; Financial Service integration is AUTHORITATIVE/DISABLED; allocation, confirmations, calendars, exceptions, corrections, and post-trade reconciliation were MISSING.
