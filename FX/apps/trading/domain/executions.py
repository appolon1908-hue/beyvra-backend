from dataclasses import dataclass


@dataclass(frozen=True)
class Execution:
    execution_id: str
    order_id: str
    provider_ref: str
