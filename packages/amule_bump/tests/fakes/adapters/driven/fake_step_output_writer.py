from pathlib import PurePath

from amule_bump.application.ports.driven.step_output_writer import StepOutputWriter


class FakeStepOutputWriter(StepOutputWriter):
    """Records each announcement, in order."""

    def __init__(self) -> None:
        self.step_outputs: list[tuple[str, PurePath]] = []

    def write_step_outputs(self, version: str, body_path: PurePath) -> None:
        self.step_outputs.append((version, body_path))
