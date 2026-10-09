# Contributing

Thank you for your interest in contributing to FluxRules!

## Code of Conduct

Be respectful, inclusive, and constructive in all interactions.

## How to contribute

### Reporting issues

- **Bugs:** Include Python version, FluxRules version, minimal reproducible example
- **Feature requests:** Describe use case and why it's needed
- **Documentation:** Point out unclear sections or missing examples

### Submitting code

1. **Fork and clone** the repository
2. **Create a branch** for your change
3. **Write tests** for new features
4. **Run tests locally** before submitting
5. **Submit a pull request** with clear description

### Development setup

```bash
# Clone repository
git clone https://github.com/fluxrules/fluxrules.git
cd fluxrules

# Install with dev extras
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run linter
ruff check src/
```

### Code style

- Follow PEP 8
- Use type hints
- Write docstrings
- Keep functions focused

### Testing standards

- Test new features thoroughly
- Keep test files organized
- Run full test suite before submitting

## Documentation

- Update docs when changing features
- Add examples for new capabilities
- Use plain, clear language
- Link to related concepts

## Questions?

Open an issue or discussion in the repository.

---

## Next Steps

- **Development** - See development/ folder for setup details
- **Architecture** - See [Architecture](architecture.md) for codebase overview
