from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from .paths import AppPaths, default_paths


@dataclass(frozen=True, slots=True)
class Settings:
    paths: AppPaths
    owner_login: str | None
    trust_tailscale_headers: bool
    model: str
    hardware_adapter: str
    codex_runtime: str
    codex_executable: str
    codex_sha256: str
    workspace: Path
    csrf_secret: str
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = os.getenv("M1LAB_DATA_DIR")
        paths = AppPaths(Path(data_dir).expanduser()) if data_dir else default_paths()
        workspace_default = paths.root / "workspace"
        return cls(
            paths=paths,
            owner_login=os.getenv("M1LAB_OWNER_LOGIN"),
            trust_tailscale_headers=os.getenv("M1LAB_TRUST_TAILSCALE_HEADERS") == "1",
            model=os.getenv("M1LAB_CODEX_MODEL", "gpt-6-sol"),
            hardware_adapter=os.getenv("M1LAB_HARDWARE_ADAPTER", "replay"),
            codex_runtime=os.getenv("M1LAB_CODEX_RUNTIME", "disabled"),
            codex_executable=os.getenv("M1LAB_CODEX_EXECUTABLE", "codex"),
            codex_sha256=os.getenv("M1LAB_CODEX_SHA256", ""),
            workspace=Path(os.getenv("M1LAB_WORKSPACE", str(workspace_default))).expanduser().resolve(),
            csrf_secret=os.getenv("M1LAB_CSRF_SECRET", ""),
            vapid_public_key=os.getenv("M1LAB_VAPID_PUBLIC_KEY", ""),
            vapid_private_key=os.getenv("M1LAB_VAPID_PRIVATE_KEY", ""),
            vapid_subject=os.getenv("M1LAB_VAPID_SUBJECT", ""),
        )
