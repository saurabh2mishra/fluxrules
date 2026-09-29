"""Shared extraction helpers for the documentation-execution harness.

Documentation defects are invisible to the ~1,660 unit tests because no test
ever executes documented code. These helpers power two checks:

* ``test_doc_imports.py``   - every documented import resolves (fast, precise)
* ``test_doc_snippets.py``  - every documented snippet executes (slower, broader)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = REPO_ROOT / "docs"

#: Fenced block opener, capturing the info string (e.g. ``python``, ``python skip``).
_FENCE_RE = re.compile(r"^(?P<indent>\s*)```(?P<info>[^\n`]*)$")

#: ``from fluxrules... import a, b as c`` - including parenthesised multi-line form.
_FROM_IMPORT_RE = re.compile(
    r"^\s*from\s+(?P<module>fluxrules[\w.]*)\s+import\s+(?P<names>\([^)]*\)|[^\n#]+)",
    re.MULTILINE,
)

#: ``import fluxrules.foo.bar`` / ``import fluxrules.foo as baz``
_PLAIN_IMPORT_RE = re.compile(r"^\s*import\s+(?P<module>fluxrules[\w.]*)", re.MULTILINE)


@dataclass(frozen=True)
class CodeBlock:
    """One fenced code block extracted from a Markdown page."""

    path: Path
    line: int
    info: str
    source: str

    @property
    def is_python(self) -> bool:
        return self.info.split()[0] in {"python", "py"} if self.info.strip() else False

    @property
    def is_skipped(self) -> bool:
        """A block is skipped if the fence says so or if the code itself declares it."""
        info_tokens = self.info.split()
        if "skip" in info_tokens[1:]:
            return True

        first_lines = [line.strip() for line in self.source.splitlines()]
        for line in first_lines:
            if line.startswith("# python skip") or line.startswith("# doctest: skip") or line.startswith("# doctest: +SKIP"):
                return True
        return False

    @property
    def rel(self) -> str:
        return str(self.path.relative_to(REPO_ROOT))


@dataclass(frozen=True)
class DocImport:
    """A single documented import symbol."""

    path: Path
    line: int
    module: str
    name: str | None  # None => plain `import module`

    @property
    def rel(self) -> str:
        return str(self.path.relative_to(REPO_ROOT))

    def __str__(self) -> str:
        if self.name is None:
            return f"import {self.module}"
        return f"from {self.module} import {self.name}"


def markdown_files(root: Path = DOCS_DIR) -> list[Path]:
    """All Markdown pages, plus the two top-level READMEs users hit first."""
    files = sorted(root.rglob("*.md"))
    for extra in (REPO_ROOT / "README.md", REPO_ROOT / "examples" / "README.md"):
        if extra.exists():
            files.append(extra)
    return files


def extract_code_blocks(path: Path) -> list[CodeBlock]:
    """Extract fenced code blocks, tracking indentation so nested fences pair up."""
    blocks: list[CodeBlock] = []
    lines = path.read_text(encoding="utf-8").splitlines()

    i = 0
    while i < len(lines):
        match = _FENCE_RE.match(lines[i])
        if not match:
            i += 1
            continue

        info = match.group("info").strip()
        indent = match.group("indent")
        # A closing fence has an empty info string at the same indent.
        start = i + 1
        j = start
        while j < len(lines):
            close = _FENCE_RE.match(lines[j])
            if close and not close.group("info").strip() and close.group("indent") == indent:
                break
            j += 1

        body = "\n".join(line.removeprefix(indent) for line in lines[start:j])
        blocks.append(CodeBlock(path=path, line=i + 1, info=info, source=body))
        i = j + 1

    return blocks


def _split_imported_names(raw: str) -> list[str]:
    """Turn an import clause into bare top-level names."""
    cleaned = raw.strip().strip("()")
    names: list[str] = []
    for part in cleaned.split(","):
        part = part.strip()
        if not part or part == "*":
            continue
        # `foo as bar` -> we must verify `foo` exists on the module.
        names.append(part.split()[0])
    return names


def extract_imports(path: Path) -> list[DocImport]:
    """Extract every documented ``fluxrules`` import from executable blocks.

    Skipped blocks are excluded: they are explicitly marked as non-executable.
    """
    found: list[DocImport] = []

    for block in extract_code_blocks(path):
        if not block.is_python or block.is_skipped:
            continue

        for match in _FROM_IMPORT_RE.finditer(block.source):
            line = block.line + block.source[: match.start()].count("\n") + 1
            for name in _split_imported_names(match.group("names")):
                found.append(
                    DocImport(path=path, line=line, module=match.group("module"), name=name)
                )

        for match in _PLAIN_IMPORT_RE.finditer(block.source):
            line = block.line + block.source[: match.start()].count("\n") + 1
            found.append(DocImport(path=path, line=line, module=match.group("module"), name=None))

    return found
