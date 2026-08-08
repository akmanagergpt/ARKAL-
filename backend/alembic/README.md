# Migrations root

Phase 1 establishes this directory as the canonical migrations root. It is
intentionally empty of runtime configuration.

`alembic.ini`, `env.py` and the first revision are **Phase 5** work
(Persistence + Project Registry + Minimal Backup/Restore) per
`docs/canonical/IMPLEMENTATION_DEPENDENCY_MATRIX.md`. Creating them now would be
configuration for a runtime that does not exist.

Migrations are always version controlled. Runtime database files never are
(see `.gitignore`).
