class LibNotFoundError(RuntimeError):
    def __init__(self, name: str, details: str = ""):
        self.name = name
        self.details = details
        super().__init__(f"Lib not found: {name} ({details})")


class LibExecutionError(RuntimeError):
    def __init__(self, name: str, message: str = "", traceback: str = ""):
        self.name = name
        self.message = message
        self.traceback = traceback
        super().__init__(f"Lib execution failed: {name}: {message}")


class LibRegistrationError(RuntimeError):
    def __init__(self, name: str, details: str = ""):
        self.name = name
        self.details = details
        super().__init__(f"Lib registration error: {name} ({details})")


class ScriptExecutionError(RuntimeError):
    def __init__(self, message: str = "", line: int | None = None):
        self.message = message
        self.line = line
        super().__init__(f"Script execution error (line {line}): {message}")


class ImmutableContextError(RuntimeError):
    def __init__(self, operation: str = ""):
        self.operation = operation
        super().__init__(f"Immutable context: {operation} is not allowed")


class LibValidationError(RuntimeError):
    def __init__(self, name: str, details: str = ""):
        self.name = name
        self.details = details
        super().__init__(f"Lib validation error: {name} ({details})")
