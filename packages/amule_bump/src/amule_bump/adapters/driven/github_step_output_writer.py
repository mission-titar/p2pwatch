from pathlib import PurePath

from amule_bump.ports.driven.step_output_writer import StepOutputWriter


class GitHubStepOutputWriter(StepOutputWriter):
    """Appends to Actions' step-outputs file, ``GITHUB_OUTPUT``; ``None`` outside Actions."""

    def __init__(self, output_path: PurePath | None) -> None:
        self._output_path = output_path

    def write_step_outputs(self, version: str, body_path: PurePath) -> None:
        if self._output_path is None:
            return
        with open(self._output_path, "a") as output:
            output.write(f"version={version}\nbody-path={body_path}\n")
