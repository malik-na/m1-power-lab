"""External-system adapters used by M1 Power Lab.

The package deliberately exposes narrow, typed interfaces.  Model output and
operator input must be turned into these types by the coordinator before an
adapter can act on them.
"""

from .hardware import (
    CaptureMemory,
    HardwareAdapter,
    HardwareCapability,
    HardwareDispatch,
    HardwareError,
    HardwareResult,
    HardwareResultStatus,
    HardwareUnavailable,
    HardwareOperation,
    InspectRegister,
    M1N1_QUALIFICATION_MESSAGE,
    M1n1HardwareAdapter,
    ReplayHardwareAdapter,
    ReplayMismatch,
    ReplayStep,
    SimulateBoot,
    TargetSnapshot,
    WaitForReplay,
)
from .runtime import (
    AppServerCodexAdapter,
    CodexRuntime,
    JobHandle,
    JobRequest,
    JobStatus,
    NoopCodexAdapter,
    RuntimeEvent,
    RuntimeErrorBase,
    RuntimeProtocolError,
    RuntimeUnavailable,
    SandboxMode,
    TokenUsage,
)

__all__ = [
    "AppServerCodexAdapter",
    "CaptureMemory",
    "CodexRuntime",
    "HardwareAdapter",
    "HardwareCapability",
    "HardwareDispatch",
    "HardwareError",
    "HardwareResult",
    "HardwareResultStatus",
    "HardwareUnavailable",
    "HardwareOperation",
    "InspectRegister",
    "JobHandle",
    "JobRequest",
    "JobStatus",
    "M1N1_QUALIFICATION_MESSAGE",
    "M1n1HardwareAdapter",
    "NoopCodexAdapter",
    "ReplayHardwareAdapter",
    "ReplayMismatch",
    "ReplayStep",
    "RuntimeEvent",
    "RuntimeErrorBase",
    "RuntimeProtocolError",
    "RuntimeUnavailable",
    "SandboxMode",
    "SimulateBoot",
    "TargetSnapshot",
    "TokenUsage",
    "WaitForReplay",
]
