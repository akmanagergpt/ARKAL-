"""`compose_real_capability_authority` — the real, composed C-13 answer
(ARKALI COMMAND CENTER — DEF-009 FLOW A CONVERGENCE AUTHORIZATION, item 3).

Every piece composed is real and unchanged (`CapabilityGraph`,
`ReferenceResolvers`, `build_capability_node`, `RequirementRegister`); only
the runtime adapter is a double, so these tests never depend on Ollama or
any other local runtime actually running on the host that executes them.
`current_phase` is supplied directly here, the same way the real
composition root (`scripts/run_command_center.py`) supplies it — this
module itself no longer asks `acceptance.engine` for it (that dependency
extended the repository's longest chain past `max_orchestration_depth`).
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from arkali.control.capability.capability_graph import CapabilityQueryResult
from arkali.control.specification.register_parser import RequirementRegister
from arkali.engineering.localai.adapter import (
    HonestState,
    LocalModelDescriptor,
    RuntimeProbeResult,
)
from arkali.engineering.localai.capability_exposure import capability_id_for
from arkali.engineering.localai.capability_query import (
    compose_real_capability_authority,
)
from arkali.kernel.contracts.capability_errors import InvalidCapabilityReference

REPO = pathlib.Path(__file__).resolve().parents[3]

DESCRIPTOR = LocalModelDescriptor(
    runtime="ollama", model_id="qwen2.5-coder:14b", parameter_size="14.8B",
    quantization="Q4_K_M", context_length=32768,
)
OVERSIZED_DESCRIPTOR = LocalModelDescriptor(
    runtime="ollama", model_id="huge-model:671b", parameter_size="671B",
    quantization="Q4_K_M", context_length=32768,
)


class _FakeAdapter:
    """A `LocalRuntimeAdapter` double: a fixed probe/model list, never a
    real network call — proves the composition, not Ollama's own
    reachability."""

    def __init__(
        self,
        probe: RuntimeProbeResult,
        models: tuple[LocalModelDescriptor, ...] = (),
    ) -> None:
        self._probe = probe
        self._models = models

    @property
    def runtime(self) -> str:
        return "ollama"

    def probe(self) -> RuntimeProbeResult:
        return self._probe

    def list_models(self) -> tuple[LocalModelDescriptor, ...]:
        return self._models

    def infer(self, model_id, prompt, *, timeout_seconds=30.0):  # noqa: ANN001, ANN201
        raise NotImplementedError("this double never performs real inference")


REACHABLE = RuntimeProbeResult(runtime="ollama", state=HonestState.PASS, detail="ok")
UNREACHABLE = RuntimeProbeResult(
    runtime="ollama", state=HonestState.EXTERNAL_UNAVAILABLE, detail="connection refused",
)


class TestComposeRealCapabilityAuthority:
    def test_a_genuinely_reachable_fitting_model_resolves_pass(self) -> None:
        adapter = _FakeAdapter(REACHABLE, (DESCRIPTOR,))
        authority = compose_real_capability_authority(REPO, adapter, '9B')
        result = authority.query(capability_id_for(DESCRIPTOR))
        assert isinstance(result, CapabilityQueryResult)
        assert result.state is HonestState.PASS

    def test_a_fitting_model_becomes_the_real_default_capability_id(self) -> None:
        """Never a hard-coded model name — derived from the real probe and
        the real, hardware-aware suitability verdict."""
        adapter = _FakeAdapter(REACHABLE, (DESCRIPTOR,))
        authority = compose_real_capability_authority(REPO, adapter, '9B')
        assert authority.default_capability_id == capability_id_for(DESCRIPTOR)

    def test_an_oversized_model_is_never_offered_as_the_default(self) -> None:
        """A model this real host's RAM cannot hold must not become the
        silently-selected default just because it exists."""
        adapter = _FakeAdapter(REACHABLE, (OVERSIZED_DESCRIPTOR,))
        authority = compose_real_capability_authority(REPO, adapter, '9B')
        assert authority.default_capability_id is None

    def test_an_unreachable_runtime_offers_no_default_and_declares_no_node(self) -> None:
        """No reachable runtime means no real descriptor was ever read, so
        no node — not even an unconfigured one — can honestly be built for
        it; `CapabilityGraph.get` raises for an id nothing declared."""
        adapter = _FakeAdapter(UNREACHABLE, (DESCRIPTOR,))
        authority = compose_real_capability_authority(REPO, adapter, '9B')
        assert authority.default_capability_id is None
        with pytest.raises(InvalidCapabilityReference):
            authority.query(capability_id_for(DESCRIPTOR))

    def test_an_unknown_capability_id_is_not_silently_configured(self) -> None:
        """A model this adapter never reported must not resolve at all."""
        adapter = _FakeAdapter(REACHABLE, (DESCRIPTOR,))
        authority = compose_real_capability_authority(REPO, adapter, '9B')
        with pytest.raises(InvalidCapabilityReference):
            authority.query("localai.ollama.a_model_never_probed")

    def test_pre_activation_answers_not_configured_even_for_a_fitting_model(
        self,
    ) -> None:
        """`current_phase != activation_phase` — the real pre-Phase-9B answer,
        proving this composition does not silently skip ADR-0003's gate."""
        adapter = _FakeAdapter(REACHABLE, (DESCRIPTOR,))
        authority = compose_real_capability_authority(REPO, adapter, "8")
        assert authority.default_capability_id is None
        result = authority.query(capability_id_for(DESCRIPTOR))
        assert result.state is HonestState.NOT_CONFIGURED

    def test_the_activation_phase_is_read_from_the_real_register_not_hardcoded(
        self,
    ) -> None:
        """`ARK-REQ-0048` carries it; a stale local constant would drift
        silently the day the register changes."""
        register = RequirementRegister.load(REPO)
        assert register.get("ARK-REQ-0048").owning_phase == "9B"

    def test_the_composition_never_imports_a_network_transport_at_module_scope(
        self,
    ) -> None:
        """The module wires adapters; it does not itself reach the network."""
        tree = ast.parse(
            (REPO / "backend" / "arkali" / "engineering" / "localai" / "capability_query.py")
            .read_text(encoding="utf-8")
        )
        imported: set[str] = set()
        for stmt in ast.walk(tree):
            if isinstance(stmt, ast.Import):
                imported |= {a.name.split(".")[0] for a in stmt.names}
            elif isinstance(stmt, ast.ImportFrom) and stmt.module:
                imported.add(stmt.module.split(".")[0])
        network = {"httpx", "requests", "urllib", "urllib3", "socket", "aiohttp"}
        assert not (imported & network), imported & network
