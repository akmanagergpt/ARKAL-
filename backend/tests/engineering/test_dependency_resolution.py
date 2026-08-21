from __future__ import annotations

import subprocess

from arkali.engineering.factory.dependency_resolution import (
    _DependencyResolutionOutcome,
    _missing_compatibility_cap_findings,
    _offline_dependency_compatibility_findings,
    _parse_requirement_specifiers,
    _resolve_backend_dependency_contract,
    _resolve_specifiers,
)
from arkali.engineering.factory.product_preflight import _dependency_compatibility_findings


def _completed(returncode: int, stderr: str = "", stdout: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["pip"], returncode=returncode, stdout=stdout, stderr=stderr)


def setup_function() -> None:
    # The resolver memoizes by exact specifier set; clear between tests so
    # a faked subprocess.run in one test cannot leak its cached verdict
    # into another test asking about the same specifiers.
    _resolve_specifiers.cache_clear()


def test_parse_requirement_specifiers_drops_comments_and_options() -> None:
    text = "flask==2.2.0\n# a comment\n\n-r other.txt\n.[extra]\nWerkzeug>=2.2  # inline\n"
    assert _parse_requirement_specifiers(text) == ["flask==2.2.0", "Werkzeug>=2.2"]


def test_empty_requirements_is_compatible_without_calling_pip(monkeypatch) -> None:  # noqa: ANN001
    calls: list[object] = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)))
    result = _resolve_backend_dependency_contract("")
    assert calls == []
    assert result.outcome is _DependencyResolutionOutcome.COMPATIBLE


def test_resolver_reports_a_real_conflict_from_pips_own_message(monkeypatch) -> None:  # noqa: ANN001
    """golden-work-047 (session evidence, frozen): the exact conflict class
    this repository failed 4/4 attempts on. `pip`'s own conflict block is
    faked here (deterministic, no network) so the parsing logic is
    verified independent of what today's real PyPI index returns; a
    separate real (unfaked) test below reproduces the live case."""
    stderr = (
        "ERROR: ResolutionImpossible: for help visit https://pip.pypa.io/...\n\n"
        "ERROR: Cannot install Werkzeug==2.1.2 and flask==2.2.0 because these "
        "package versions have conflicting dependencies.\n\n"
        "The conflict is caused by:\n"
        "    The user requested Werkzeug==2.1.2\n"
        "    flask 2.2.0 depends on Werkzeug>=2.2.0\n"
    )
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _completed(1, stderr=stderr))
    result = _resolve_backend_dependency_contract("flask==2.2.0\nWerkzeug==2.1.2\n")
    assert result.outcome is _DependencyResolutionOutcome.CONFLICT
    assert "Werkzeug==2.1.2" in result.detail
    assert "flask 2.2.0 depends on Werkzeug>=2.2.0" in result.detail


def test_resolver_reports_compatible_on_a_real_pip_success(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _completed(0))
    result = _resolve_backend_dependency_contract("flask==2.2.0\nWerkzeug==2.2.0\n")
    assert result.outcome is _DependencyResolutionOutcome.COMPATIBLE


def test_resolver_reports_not_configured_when_pip_cannot_run(monkeypatch) -> None:  # noqa: ANN001
    """Never a silent COMPATIBLE on an unavailable toolchain (this
    repository's own convention: PASS FAIL BLOCKED NOT_TESTED
    NOT_CONFIGURED, never a fabricated pass)."""

    def raise_missing(*args: object, **kwargs: object) -> subprocess.CompletedProcess:
        raise FileNotFoundError("no pip")

    monkeypatch.setattr(subprocess, "run", raise_missing)
    result = _resolve_backend_dependency_contract("flask==2.2.0\n")
    assert result.outcome is _DependencyResolutionOutcome.NOT_CONFIGURED


def test_resolver_reports_not_configured_on_timeout(monkeypatch) -> None:  # noqa: ANN001
    def raise_timeout(*args: object, **kwargs: object) -> subprocess.CompletedProcess:
        raise subprocess.TimeoutExpired(cmd="pip", timeout=45.0)

    monkeypatch.setattr(subprocess, "run", raise_timeout)
    result = _resolve_backend_dependency_contract("flask==2.2.0\n")
    assert result.outcome is _DependencyResolutionOutcome.NOT_CONFIGURED


def test_resolver_reports_not_configured_on_an_unrecognized_pip_failure(monkeypatch) -> None:  # noqa: ANN001
    """A non-zero exit that is not a real ResolutionImpossible conflict
    (e.g. a network error) must not be misreported as a dependency
    conflict — it degrades to NOT_CONFIGURED, triggering the offline
    fallback, not a fabricated finding."""
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: _completed(1, stderr="Could not find a version")
    )
    result = _resolve_backend_dependency_contract("flask==2.2.0\n")
    assert result.outcome is _DependencyResolutionOutcome.NOT_CONFIGURED


def test_missing_compatibility_cap_fires_for_unpinned_werkzeug_on_old_flask() -> None:
    """Real, verified ecosystem gap (module docstring): Flask 2.0.1's own
    published metadata declares no Werkzeug upper bound, so `pip` alone
    cannot see this — it must always run regardless of resolver verdict."""
    findings = _missing_compatibility_cap_findings("flask==2.0.1\n")
    assert any(code == "incompatible_dependency_range" for code, _, _ in findings)


def test_missing_compatibility_cap_is_silent_when_a_cap_is_declared() -> None:
    findings = _missing_compatibility_cap_findings("flask==2.0.1\nwerkzeug<3\n")
    assert findings == []


def test_missing_compatibility_cap_fires_for_flask_sqlalchemy() -> None:
    findings = _missing_compatibility_cap_findings("flask_sqlalchemy==2.5.1\n")
    assert any(code == "incompatible_dependency_range" for code, _, _ in findings)


def test_offline_fallback_still_catches_the_resolver_only_case() -> None:
    """Without a resolver verdict, the full offline table must still catch
    a Werkzeug pin below Flask's own declared, accurate lower bound —
    golden-work-047's exact class — so that case is not silently lost
    when `pip` is unavailable."""
    findings = _offline_dependency_compatibility_findings("flask==2.2.0\nwerkzeug==2.1.2\n")
    assert any("2.2" in detail for _, _, detail in findings)


def test_dispatcher_falls_back_to_the_offline_table_when_the_resolver_is_not_configured(
    monkeypatch,  # noqa: ANN001
) -> None:
    def raise_missing(*args: object, **kwargs: object) -> subprocess.CompletedProcess:
        raise FileNotFoundError("no pip")

    monkeypatch.setattr(subprocess, "run", raise_missing)
    findings = _dependency_compatibility_findings("flask==2.2.0\nwerkzeug==2.1.2\n")
    assert any(f.code == "incompatible_dependency_range" for f in findings)


def test_dispatcher_reports_the_resolvers_own_conflict_when_available(monkeypatch) -> None:  # noqa: ANN001
    stderr = (
        "ERROR: ResolutionImpossible: for help visit https://pip.pypa.io/...\n\n"
        "The conflict is caused by:\n"
        "    The user requested Werkzeug==2.1.2\n"
        "    flask 2.2.0 depends on Werkzeug>=2.2.0\n"
    )
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _completed(1, stderr=stderr))
    findings = _dependency_compatibility_findings("flask==2.2.0\nwerkzeug==2.1.2\n")
    assert [f.detail for f in findings if f.code == "incompatible_dependency_range"] == [
        "The user requested Werkzeug==2.1.2; flask 2.2.0 depends on Werkzeug>=2.2.0",
    ]


def test_dispatcher_is_silent_on_a_real_compatible_set(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _completed(0))
    findings = _dependency_compatibility_findings("requests==2.31.0\n")
    assert findings == []


# --- Real (unfaked) end-to-end evidence -------------------------------------
# These two hit the real `pip` resolver against the real package index, the
# same way `_resolve_backend_dependency_contract` runs in production. Slower
# than the faked tests above and require network, but they are the only
# tests in this file that prove the real ARK-ERR-0116 golden-work-047 class
# is actually caught by real evidence, not just a hand-substituted stand-in.


def test_real_pip_reports_the_golden_work_047_conflict() -> None:
    result = _resolve_backend_dependency_contract("flask==2.2.0\nWerkzeug==2.1.2\n")
    assert result.outcome is _DependencyResolutionOutcome.CONFLICT
    assert "werkzeug" in result.detail.lower()


def test_real_pip_reports_a_genuinely_compatible_pair() -> None:
    result = _resolve_backend_dependency_contract("flask==2.2.0\nWerkzeug==2.2.0\n")
    assert result.outcome is _DependencyResolutionOutcome.COMPATIBLE
