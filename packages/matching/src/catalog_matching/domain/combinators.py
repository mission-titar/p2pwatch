"""``Matcher`` and the ``all``/``any``/``not`` combinators (cf. spec §8.3).

Pure domain: these combinators wrap other ``Matcher``s (Plan 2a leaves or combinators) and
expose the same ``matches(candidate) -> bool`` interface.
"""

from abc import ABC, abstractmethod

from catalog_matching.domain.models import FileCandidate


class Matcher(ABC):
    """What the leaves (Plan 2a) and the combinators promise; ``CoverageMatcher.coverage()``
    is not part of it, the explanation reads it directly."""

    @abstractmethod
    def matches(self, candidate: FileCandidate) -> bool:
        """Whether the candidate matches."""


class AllMatcher(Matcher):
    """Conjunction: true if ALL children match (``all([]) == True``)."""

    def __init__(self, children: tuple[Matcher, ...]) -> None:
        self._children = children

    def matches(self, candidate: FileCandidate) -> bool:
        return all(child.matches(candidate) for child in self._children)


class AnyMatcher(Matcher):
    """Disjunction: true if AT LEAST one child matches (``any([]) == False``)."""

    def __init__(self, children: tuple[Matcher, ...]) -> None:
        self._children = children

    def matches(self, candidate: FileCandidate) -> bool:
        return any(child.matches(candidate) for child in self._children)


class NotMatcher(Matcher):
    """Negation: true if the single child does NOT match."""

    def __init__(self, child: Matcher) -> None:
        self._child = child

    def matches(self, candidate: FileCandidate) -> bool:
        return not self._child.matches(candidate)
