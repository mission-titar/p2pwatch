"""The error a refused config raises, carrying every problem of its files."""

from p2pwatch.domain.config_problem import ConfigProblem


class InvalidConfigError(Exception):
    """The config refuses the crawl: ``problems``, never empty, are every problem its files hold."""

    def __init__(self, problems: tuple[ConfigProblem, ...]) -> None:
        if not problems:
            raise ValueError("an invalid config holds at least one problem")
        super().__init__(problems)
        self.problems = problems
