# Changelog

## Version Overview

FluxRules follows semantic versioning.

### Latest Changes

For the most up-to-date changes, see `CHANGELOG.md` in the repository root or the git commit log.

### Key Milestones

- **v0.0.1** (2026) — Initial, unpublished development version
  - PHREAK engine (single engine)
  - Stateless and streaming evaluation modes
  - Pydantic v2 rule validation
  - Extensible engines, operators, actions, and transforms
  - Optional FastAPI REST API
  - Fact pipeline transforms
  - Custom actions system

### Stability

- **Core API**: Stable (Rule, Engine, evaluate())
- **DSL format**: Stable
- **Endpoints**: Stable under `/api/v1`

### Upgrade path

Breaking changes will be released under `/api/v2` to maintain backward compatibility.

---

## Next Steps

- **Contributing** — See [Contributing](contributing.md)
- **Architecture** — See [Architecture](architecture.md)
