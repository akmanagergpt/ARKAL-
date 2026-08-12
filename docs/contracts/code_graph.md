# C-24 — Code graph / Digital Twin view

**Owner:** `engineering.codeintel` · **Kind:** GRAPH · **Versioning:** semver ·
**Compatibility:** ADDITIVE · **Phase:** 11

This is a derived description of the implemented contract. The canonical
architecture, requirement register and contract inventory remain authoritative.

## Contract

`GraphVocabulary` reads the graph kinds and Digital Twin views from
`ARCHITECTURE.md` §11 at call time. A kind or view outside that vocabulary is
refused. The vocabulary and its size are not duplicated in shipping source.

`CodeGraph` is a derived store of sourced nodes and directed edges. Its content
address is calculated from a sorted, duplicate-free rendering, so rebuilding
identical facts is deterministic regardless of insertion or filesystem order.
`assert_rebuild_matches` refuses a differing rebuild. `PythonGraphBuilder` uses
native AST over Python source and reports exactly which graph kinds it can
build; asking it for an adapter it does not implement is refused rather than
returned as an empty graph.

`DigitalTwin` composes every canonical view exactly once and in canonical
order. Each view is either backed by canonical artifact addresses or carries an
explicit absence reason. Missing, duplicate, unknown, empty and ambiguous
contributions are refused.

Both `CodeGraph.resolve_authority` and `DigitalTwin.resolve_authority` always
refuse. The graph and twin point back to their sources; they never replace the
owning authorities.

## Compatibility

ADDITIVE means later canonical revisions may add graph kinds, view kinds, node
facts or edge facts without invalidating existing consumers. Removing or
reinterpreting an existing kind or fact is not additive. Producers still reject
undeclared fields and unknown vocabulary entries; ADDITIVE does not permit a
caller to invent them.

## Evidence and limits

Rebuild determinism is C-24's inventory-declared verification responsibility.
The contract and integration suites build real graphs from repository Python
source twice and compare their canonical addresses. The composed Phase 11
journey then supplies those addresses to the code view and declares every view
without a Phase 11 adapter honestly absent.

Phase 11 does not deliver Tree-sitter adapters, framework-semantic route or
model adapters, runtime/deployment collectors, persistence, or an authoritative
query surface. No table, migration, state machine, provider call or external
result is part of C-24.
