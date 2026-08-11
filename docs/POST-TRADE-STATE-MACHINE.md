# Post-Trade State Machine

State changes use an explicit transition matrix from `CAPTURED` through validation, allocation, and settlement instruction. Terminal regression is rejected; `SETTLED` can only enter an explicit reversal flow. Mismatches enter `EXCEPTION` and are never silently advanced.
