"""``ExpectedError``: the base of every error a driven port declares, in the domain since both
sides use it."""


class ExpectedError(Exception):
    """An error the code expects from outside, such as aMule down, a search refused or a full
    disk; any other exception is a bug."""
