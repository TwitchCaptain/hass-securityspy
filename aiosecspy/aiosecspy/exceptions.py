"""Exceptions for aiosecspy."""


class SecSpyError(Exception):
    """Base error for SecuritySpy client failures."""


class AuthenticationError(SecSpyError):
    """Invalid credentials or unauthorized response."""


class UnsupportedError(SecSpyError):
    """Server does not support the requested operation."""


class RequestError(SecSpyError):
    """HTTP or transport failure talking to SecuritySpy."""
