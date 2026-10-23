class BrokenInputError(Exception):
    """An input a check cannot read, its message naming the file; the command line prints it and
    returns 1."""
