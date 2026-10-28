"""FluxRules command-line interface.

The ``fluxrules`` console script points at :func:`run` rather than at the
Typer app directly, so a base install without the ``cli`` extra prints an
install hint instead of a ``ModuleNotFoundError`` traceback.
"""

from __future__ import annotations

import sys

# Third-party packages provided by the ``fluxrules[cli]`` extra.
_CLI_DEPENDENCIES = frozenset({"typer", "click", "rich"})


def run() -> None:
    """Run the ``fluxrules`` CLI, or explain how to install it.

    Named ``run`` rather than ``main`` because importing the ``main`` submodule
    rebinds ``fluxrules.cli.main`` to that module.
    """
    try:
        from fluxrules.cli.main import app
    except ModuleNotFoundError as exc:
        missing = (exc.name or "").partition(".")[0]
        if missing not in _CLI_DEPENDENCIES:
            raise
        print(
            f"The fluxrules CLI needs the 'cli' extra ({missing} is not installed).\n"
            "Install it with: pip install 'fluxrules[cli]'",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    app()
