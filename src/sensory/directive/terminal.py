from common import config
from dtos.directive_terminal import DirectiveTerminalDto


def execute() -> DirectiveTerminalDto:
    """
    ターミナルからの外部指示（指令）を読み取る
    """

    text = input(config.UI_INPUT_LABEL).strip()

    if text == config.COMMAND_END:
        raise EOFError

    return DirectiveTerminalDto(t=text)
