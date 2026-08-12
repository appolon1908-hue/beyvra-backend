class OperationalModeResolver:
    PRECEDENCE=(("global_halt","HALTED"),("security_halt","HALTED"),("financial_halt","SIMULATION_ONLY"),("execution_halt","SIMULATION_ONLY"),("dependency_failure","READ_ONLY"),("capacity_restriction","DEGRADED"),("data_stale","DEGRADED"))
    MATRIX={"HEALTHY":{"read","simulate"},"DEGRADED":{"read","limited_simulation"},"READ_ONLY":{"read"},"SIMULATION_ONLY":{"read","simulate"},"HALTED":set(),"UNAVAILABLE":set()}
    @classmethod
    def resolve(cls,signals):
        for key,mode in cls.PRECEDENCE:
            if signals.get(key) is True:return mode
            if signals.get(key) is None and key in {"global_halt","security_halt","financial_halt","execution_halt"}:return "HALTED"
        return "HEALTHY"
    @classmethod
    def allows(cls,mode,capability):return capability in cls.MATRIX.get(mode,set())
