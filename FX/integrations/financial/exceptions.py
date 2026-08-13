class FinancialServiceError(RuntimeError):
    pass


class FinancialMutationDisabled(FinancialServiceError):
    pass
