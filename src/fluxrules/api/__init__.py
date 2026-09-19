"""FluxRules API package (optional - requires `pip install fluxrules[api]`)."""

__all__ = ["create_app"]


def create_app():
    """Lazy import to avoid pulling in FastAPI/SQLAlchemy at library import time."""
    from fluxrules.api.app import create_app as _create_app

    return _create_app()
