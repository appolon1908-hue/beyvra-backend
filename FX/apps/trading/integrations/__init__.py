"""Trading integration boundary; concrete clients live under top-level integrations."""

from integrations.execution import ExecutionProvider
from integrations.financial import FinancialClient

__all__ = ("ExecutionProvider", "FinancialClient")
