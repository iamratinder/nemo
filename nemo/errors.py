"""Failures that should reach the user as a message, not a traceback."""


class NemoError(Exception):
    """A request or response problem the user can act on."""
