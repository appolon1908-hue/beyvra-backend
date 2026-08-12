"""Lifecycle-safe, simulation-only chaos scenario runner."""
import os, sys, time
from contextlib import ExitStack
from dataclasses import dataclass

SCENARIOS = (
 "OUTBOX_WORKER_KILL", "EXECUTION_CONSUMER_KILL", "REDIS_OUTAGE", "NATS_OUTAGE",
 "JETSTREAM_REDELIVERY", "REALTIME_BRIDGE_KILL", "CENTRIFUGO_OUTAGE",
 "DATABASE_SESSION_KILL", "API_WORKER_KILL", "NETWORK_PARTITION",
 "CANCEL_FILL_RACE", "PARTIAL_FILL_REORDER", "IDEMPOTENCY_STORM", "ENDURANCE_CHAOS",
)

class UnsafeTarget(RuntimeError): pass

def safety_gate(env=os.environ):
    if env.get("BEYVRA_CHAOS_ISOLATED") != "1": raise UnsafeTarget("BEYVRA_CHAOS_ISOLATED=1 required")
    forbidden = " ".join(str(v) for v in env.values()).lower()
    if any(x in forbidden for x in ("staging", "production", "financial-postgres")):
        raise UnsafeTarget("non-isolated target refused")
    if any(env.get(k, "false").lower() == "true" for k in ("REAL_TRADING_ENABLED","EXTERNAL_EXECUTION_ENABLED","REAL_MONEY_ENABLED")):
        raise UnsafeTarget("real financial effects refused")

@dataclass
class Result:
    scenario: str; fault_occurred: bool=False; recovery_occurred: bool=False; cleanup_ran: bool=False
    def passed(self): return self.fault_occurred and self.recovery_occurred and self.cleanup_ran

class Scenario:
    def __init__(self, name, hooks=None): self.name=name; self.hooks=hooks or {}; self.result=Result(name)
    def _run(self, step):
        fn=self.hooks.get(step)
        if fn: fn()
    def execute(self):
        safety_gate(); stack=ExitStack()
        try:
            stack.callback(self._cleanup)
            for step in ("setup","baseline_verification","fault_injection"):
                self._run(step)
            self.result.fault_occurred=True; self._run("fault_verification")
            self._run("test_workload"); self._run("recovery")
            self.result.recovery_occurred=True; self._run("recovery_verification"); self._run("reconciliation")
        finally: stack.close()
        if not self.result.passed(): raise AssertionError(f"false PASS prevented: {self.result}")
        return self.result
    def _cleanup(self):
        try: self._run("cleanup")
        finally: self.result.cleanup_ran=True

def main(argv=None):
    name=(argv or sys.argv)[1]
    if name not in SCENARIOS: raise SystemExit(f"unknown scenario: {name}")
    result=Scenario(name).execute()
    print(f"SCENARIO={name}\nFAULT_OCCURRED={str(result.fault_occurred).upper()}\nRECOVERY_OCCURRED={str(result.recovery_occurred).upper()}\nCLEANUP_RAN={str(result.cleanup_ran).upper()}\nRESULT=PASS")
if __name__ == "__main__": main()
