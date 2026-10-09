from dataclasses import dataclass, field

from anima_ll.domain.model.identifiers import JsonValue, PulseNumber


class RuntimeEventType:
    RUN = "run"            # 起動時に 1 回：どの設計図・環境・個体で動いたか
    PULSE = "pulse"
    VIEW = "view"
    # 計算の意図の一生（計算資源境界 仕様 v0.3.1 §2.3）
    INTENT_CREATED = "intent_created"
    INTENT_ADMITTED = "intent_admitted"
    INTENT_REJECTED_OVERFLOW = "intent_rejected_overflow"  # 列のあふれ。Kernel の失敗とは別
    INTENT_STARTED = "intent_started"
    INTENT_COMPLETED = "intent_completed"
    INTENT_KERNEL_ERROR = "intent_kernel_error"
    INTENT_OUTSTANDING = "intent_outstanding"  # run の終了時点で実行中・待ちのまま残った意図
    RUNTIME_DEGRADED = "runtime_degraded"      # 実行基盤の劣化（あふれ）。この run の結果は認知として解釈しない
    SENSORY = "sensory"    # Receptor が成立させた感覚の出来事（活動の伝達 仕様 §4）
    ACTIVITY = "activity"  # Unit が成立させた発火の出来事（同 §2・接続の状態 仕様 §4）
    DELTA = "delta"
    EFFECT = "effect"
    VIOLATION = "violation"
    UNROUTED = "unrouted"
    UNIT_STATE = "unit_state"  # 観察用：Unit の私的な状態の標本（間隔は設定で決める。既定は記録しない）


@dataclass(frozen=True)
class RuntimeEvent:
    """来歴ログの 1 行。あとから因果を辿るために、Runtime の出来事をすべて記録する。"""

    type: str
    pulse: PulseNumber
    data: dict[str, JsonValue] = field(default_factory=dict)
