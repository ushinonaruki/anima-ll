import os
from dtos.directive_terminal import DirectiveTerminalDto

COMMAND_END: str = os.environ.get("COMMAND_END")
INPUT_LABEL: str = os.environ.get("INPUT_LABEL")


def execute() -> DirectiveTerminalDto:
    """
    ターミナルからの外部指示（指令）を読み取る
    """

    text = input(INPUT_LABEL).strip()

    if text == COMMAND_END:
        raise EOFError

    return DirectiveTerminalDto(t=text)
