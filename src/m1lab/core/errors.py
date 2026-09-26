class CoreError(RuntimeError):
    """Base error exposed by the core interface."""


class NotFoundError(CoreError):
    pass


class ConflictError(CoreError):
    pass


class ValidationError(CoreError):
    pass


class IneligibleError(CoreError):
    pass
