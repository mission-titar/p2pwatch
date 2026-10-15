"""The lines of a module inside a function's body: only a call runs them, never its import."""

import ast
from collections.abc import Iterator


def find_function_body_lines(source: str) -> frozenset[int]:
    """Every line of the functions' bodies in *source*; a one-line `def` runs at import."""
    body_lines: set[int] = set()
    for function in _outermost_functions(ast.parse(source)):
        body_lines.update(range(function.body[0].lineno, (function.end_lineno or 0) + 1))
        body_lines.discard(function.lineno)
    return frozenset(body_lines)


def _outermost_functions(node: ast.AST) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
            yield child
        else:
            yield from _outermost_functions(child)
