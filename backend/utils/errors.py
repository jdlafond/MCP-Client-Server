class AgentError(Exception):
    """Base exception for agent errors"""
    pass

class BudgetExceededError(AgentError):
    """Raised when agent exceeds time or step budgets"""
    pass

class LoopDetectedError(AgentError):
    """Raised when tool call loop is detected"""
    pass

class TaigaError(AgentError):
    """Raised when Taiga API fails"""
    pass

class PermissionDeniedError(AgentError):
    """Raised when user lacks required permissions"""
    pass
