"""Unit tests for OCI Vault CLI response handling."""

from deployment.security.vault import OciVaultConfiguration, OciVaultSecretClient


class EmptyListRunner:
    """Return successful empty stdout for OCI list operations."""

    def run(self, argv: tuple[str, ...]) -> str:
        return ""


def _client() -> OciVaultSecretClient:
    return OciVaultSecretClient(
        OciVaultConfiguration(
            compartment_ocid="ocid1.compartment.test",
            vault_ocid="ocid1.vault.test",
            key_ocid="ocid1.key.test",
        ),
        runner=EmptyListRunner(),
    )


def test_get_returns_none_when_oci_list_stdout_is_empty() -> None:
    """A successful empty list response means the requested secret is absent."""

    assert _client().get("anu-masker-key") is None


def test_list_names_returns_empty_when_oci_list_stdout_is_empty() -> None:
    """Empty OCI list stdout is equivalent to an empty Vault result set."""

    assert _client().list_names() == ()


class RecordingRunner:
    """Record OCI commands and JSON payloads while returning controlled responses."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)
        self.payloads: list[dict[str, object]] = []

    def run(self, argv: tuple[str, ...]) -> str:
        if "--from-json" in argv:
            import json
            from pathlib import Path

            value = argv[argv.index("--from-json") + 1]
            self.payloads.append(json.loads(Path(value.removeprefix("file://")).read_text()))
            return "{}"
        return next(self.responses)


def test_put_create_waits_for_active_without_fixed_content_name() -> None:
    """Creating a secret waits for ACTIVE and lets OCI assign the content version name."""

    runner = RecordingRunner(['{"data": []}'])
    client = OciVaultSecretClient(
        OciVaultConfiguration(
            compartment_ocid="ocid1.compartment.test",
            vault_ocid="ocid1.vault.test",
            key_ocid="ocid1.key.test",
        ),
        runner=runner,
    )

    client.put("anu-test", b"value")

    payload = runner.payloads[0]
    assert "secretContentName" not in payload
    assert payload["waitForState"] == ["ACTIVE"]
    assert payload["maxWaitSeconds"] == 300
    assert payload["waitIntervalSeconds"] == 2


def test_put_update_waits_for_active_without_fixed_content_name() -> None:
    """Updating a secret publishes a new version and waits until it becomes ACTIVE."""

    import base64
    import json

    current = base64.b64encode(b"old").decode("ascii")
    runner = RecordingRunner(
        [
            json.dumps({"data": [{"secret-name": "anu-test", "id": "ocid1.vaultsecret.test"}]}),
            json.dumps({"data": {"secret-bundle-content": {"content": current}}}),
        ]
    )
    client = OciVaultSecretClient(
        OciVaultConfiguration(
            compartment_ocid="ocid1.compartment.test",
            vault_ocid="ocid1.vault.test",
            key_ocid="ocid1.key.test",
        ),
        runner=runner,
    )

    client.put("anu-test", b"new")

    payload = runner.payloads[0]
    assert payload["secretId"] == "ocid1.vaultsecret.test"
    assert "secretContentName" not in payload
    assert payload["waitForState"] == ["ACTIVE"]
