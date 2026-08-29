"""Unit tests for OCI CLI subprocess error reporting."""

import subprocess

import pytest

from deployment.security.vault import SubprocessCommandRunner


def test_subprocess_runner_surfaces_oci_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    """OCI service errors remain visible instead of becoming opaque CalledProcessError failures."""

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=("oci", "vault", "secret", "update-base64"),
            returncode=1,
            stdout="",
            stderr="ServiceError: NotAuthorizedOrNotFound",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="NotAuthorizedOrNotFound"):
        SubprocessCommandRunner().run(("oci", "vault", "secret", "update-base64"))
