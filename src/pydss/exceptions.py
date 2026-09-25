"""Exceptions used in Pydss"""


class InvalidConfigurationError(Exception):
    """Raised when a bad configuration is detected."""


class InvalidParameterError(Exception):
    """Raised when bad user input is detected."""


class OpenDssConvergenceError(Exception):
    """Raised when OpenDSS fails to converge on a solution."""


class OpenDssConvergenceErrorCountExceededError(Exception):
    """Raised when OpenDSS exceeds the threshold of convergence error counts."""


class OpenDssModelError(Exception):
    """Raised when OpenDSS fails to compile a model."""


class PyDssConvergenceError(Exception):
    """Raised when pydss fails to converge on a solution."""


class PyDssConvergenceMaxError(Exception):
    """Raised when pydss exceeds a max convergence error threshold."""


class PyDssConvergenceErrorCountExceededError(Exception):
    """Raised when pydss exceeds the threshold of convergence error counts."""


InvalidConfiguration = InvalidConfigurationError
InvalidParameter = InvalidParameterError
OpenDssConvergenceErrorCountExceeded = OpenDssConvergenceErrorCountExceededError
PyDssConvergenceErrorCountExceeded = PyDssConvergenceErrorCountExceededError
