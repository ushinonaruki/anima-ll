from .directive_terminal import DirectiveTerminalDto
from .site_jma import SiteJmaDto
from .body_system import BodySystemDto
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AnimaLlPacket:
    cmd: Optional[DirectiveTerminalDto] = None
    jma: Optional[SiteJmaDto] = None
    sys: Optional[BodySystemDto] = None

    def serialize(self) -> str:
        """
        全感覚を結合し、脳が認識可能なRawデータブロックに変換
        """

        lines = ["[!]"]

        if self.cmd:
            lines.append(f"cmd>{self.cmd.to_kv()}")

        if self.jma:
            lines.append(f"jma>{self.jma.to_kv()}")

        if self.sys:
            lines.append(f"sys>{self.sys.to_kv()}")

        return "\n".join(lines)
