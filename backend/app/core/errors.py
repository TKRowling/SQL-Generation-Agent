class AskMeError(Exception):
    """Base application exception."""


class ConfigurationError(AskMeError):
    pass


class ForbiddenQueryError(AskMeError):
    def __init__(self, message: str = "Query references a forbidden credential column.") -> None:
        super().__init__(message)


class DatabaseUnavailableError(AskMeError):
    pass


class AIUnavailableError(AskMeError):
    pass


class AIResponseError(AskMeError):
    pass
