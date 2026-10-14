"""Control-flow exceptions shared across the package."""


class PaymentRequiredError(Exception):
    """Raised on HTTP 402 from Token Factory (out of credit mid-call)."""


class BudgetStop(Exception):
    """Raised when the local BUDGET_USD guard trips during a run."""
