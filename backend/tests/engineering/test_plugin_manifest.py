"""C-30 plugin manifest contract (ARK-REQ-0164: manifest/permission/version
governed).

Phase 21 Package 1.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from arkali.engineering.plugin.errors import PluginManifestVersionError
from arkali.engineering.plugin.manifest import CONTRACT_VERSION, PluginManifest, is_semver


def _manifest(**overrides: object) -> PluginManifest:
    fields: dict[str, object] = {
        "plugin_id": "acme.example-plugin",
        "name": "Example Plugin",
        "version": "1.2.3",
        "declared_permissions": ("READ_FILE",),
    }
    fields.update(overrides)
    return PluginManifest(**fields)  # type: ignore[arg-type]


class TestSemverValidation:
    @pytest.mark.parametrize(
        "version",
        ["0.0.1", "1.0.0", "12.34.56", "1.0.0-alpha", "1.0.0-alpha.1",
         "1.0.0+build.5", "1.0.0-beta+exp.sha.5114f85"],
    )
    def test_valid_semver_versions_are_accepted(self, version: str) -> None:
        assert _manifest(version=version).version == version

    @pytest.mark.parametrize(
        "version",
        ["1", "1.0", "v1.0.0", "1.0.0.0", "01.0.0", "1.00.0", "latest", "",
         "1.0.0-", "1.0.0+"],
    )
    def test_invalid_versions_are_refused(self, version: str) -> None:
        with pytest.raises((PluginManifestVersionError, ValidationError)):
            _manifest(version=version)

    def test_is_semver_matches_the_same_rule_the_model_enforces(self) -> None:
        assert is_semver("2.1.0") is True
        assert is_semver("not-a-version") is False


class TestManifestIdentityAndVersion:
    def test_contract_version_defaults(self) -> None:
        assert _manifest().contract_version == CONTRACT_VERSION

    def test_manifest_is_frozen(self) -> None:
        manifest = _manifest()
        with pytest.raises(ValidationError):
            manifest.version = "9.9.9"  # type: ignore[misc]

    def test_extra_fields_are_refused(self) -> None:
        with pytest.raises(ValidationError):
            PluginManifest(
                plugin_id="acme.x", name="X", version="1.0.0",
                declared_permissions=(), unexpected="nope",  # type: ignore[call-arg]
            )

    def test_empty_plugin_id_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            _manifest(plugin_id="")

    def test_declared_permissions_default_to_empty(self) -> None:
        manifest = PluginManifest(plugin_id="acme.x", name="X", version="1.0.0")
        assert manifest.declared_permissions == ()


class TestManifestRefIsContentAddressed:
    def test_identical_manifests_share_a_ref(self) -> None:
        assert _manifest().manifest_ref == _manifest().manifest_ref

    def test_a_changed_field_changes_the_ref(self) -> None:
        assert _manifest().manifest_ref != _manifest(version="1.2.4").manifest_ref

    def test_permission_order_is_not_normalised_by_this_type(self) -> None:
        """`declared_permissions` is an ordered tuple: the manifest records
        exactly what the author declared, in the order declared. Any
        normalisation (e.g. de-duplication, sorting) is a pipeline concern,
        not this contract's."""
        a = _manifest(declared_permissions=("READ_FILE", "RUN_PROCESS"))
        b = _manifest(declared_permissions=("RUN_PROCESS", "READ_FILE"))
        assert a.manifest_ref != b.manifest_ref

    def test_ref_is_a_canonical_content_address(self) -> None:
        from arkali.kernel.contracts.content_address import is_address

        assert is_address(_manifest().manifest_ref)
