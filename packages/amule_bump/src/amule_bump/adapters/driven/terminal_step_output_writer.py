from pathlib import PurePath

from amule_bump.ports.driven.step_output_writer import StepOutputWriter


class TerminalStepOutputWriter(StepOutputWriter):
    """Prints the step outputs, for a bump run by hand outside Actions."""

    def write_step_outputs(self, version: str, body_path: PurePath) -> None:
        print(f"version={version}\nbody-path={body_path}")
