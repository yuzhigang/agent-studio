from src.runtime.lib.exceptions import (
    LibNotFoundError,
    LibExecutionError,
    LibRegistrationError,
    ScriptExecutionError,
    ImmutableContextError,
    LibValidationError,
)


def test_exceptions_are_runtime_error_subclasses():
    assert issubclass(LibNotFoundError, RuntimeError)
    assert issubclass(LibExecutionError, RuntimeError)
    assert issubclass(LibRegistrationError, RuntimeError)
    assert issubclass(ScriptExecutionError, RuntimeError)
    assert issubclass(ImmutableContextError, RuntimeError)
    assert issubclass(LibValidationError, RuntimeError)


def test_lib_not_found_error_carries_details():
    e = LibNotFoundError("foo.bar", details="not registered")
    assert e.name == "foo.bar"
    assert "not registered" in str(e)
