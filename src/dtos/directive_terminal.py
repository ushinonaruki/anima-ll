from dataclasses import dataclass


@dataclass(frozen=True)
class DirectiveTerminalDto:
    """
    ターミナルに直接入力された値
    """

    # 文字列 (Text)
    t: str

    def to_kv(self) -> str:
        return f"t:{self.t}"
