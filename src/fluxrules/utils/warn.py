"""Point a warning at the user's code, not at the fluxrules line that noticed it."""

from __future__ import annotations

import os
import sys
from types import FrameType

__all__ = ["caller_stacklevel"]

_FLUXRULES_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PYDANTIC_MARKER = f"{os.sep}pydantic{os.sep}"


def caller_stacklevel() -> int:
    """Stack level of the first frame outside fluxrules and pydantic.

    Pass it as ``warnings.warn(..., stacklevel=caller_stacklevel())`` from the
    function that emits the warning. The warning then points at the line that
    wrote the rule or called the engine, not at the validator that noticed the
    problem. The ``__init__`` that ``dataclasses`` generates (file
    ``<string>``) is skipped too.
    """
    level = 1
    frame: FrameType | None = sys._getframe(1)
    while frame is not None:
        code = frame.f_code
        generated_init = code.co_filename == "<string>" and code.co_name == "__init__"
        filename = os.path.abspath(code.co_filename)
        if (
            not generated_init
            and not filename.startswith(_FLUXRULES_DIR)
            and _PYDANTIC_MARKER not in filename
        ):
            return level
        frame = frame.f_back
        level += 1
    return level  # pragma: no cover - defensive: some caller is always outside fluxrules
