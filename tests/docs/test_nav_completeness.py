"""Every documentation page must be reachable from the mkdocs nav.

51% of pages (31 of 61) were orphaned - invisible on the published site -
including `benchmarks`, `choosing-an-engine`, and `deployment`: exactly the
pages evaluators look for. Step 10 surfaced them; this test stops it recurring
the moment someone adds a page.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = REPO_ROOT / "docs"
MKDOCS_YML = REPO_ROOT / "mkdocs.yml"

#: Pages deliberately excluded from the nav, each with a justification.
#: Adding to this list should be a conscious decision, not a reflex.
ALLOWED_ORPHANS: dict[str, str] = {}


def _nav_referenced_pages() -> set[str]:
    """All ``*.md`` paths mentioned anywhere in mkdocs.yml."""
    return set(re.findall(r"([A-Za-z0-9_./-]+\.md)", MKDOCS_YML.read_text()))


def test_no_orphan_docs() -> None:
    """Every docs page is in the nav or on the explicit allowlist."""
    all_pages = {str(p.relative_to(DOCS_DIR)) for p in DOCS_DIR.rglob("*.md")}
    orphans = all_pages - _nav_referenced_pages() - set(ALLOWED_ORPHANS)

    assert not orphans, (
        "These docs pages are unreachable from the mkdocs nav:\n  "
        + "\n  ".join(sorted(orphans))
        + "\n\nAdd them to `nav:` in mkdocs.yml, or to ALLOWED_ORPHANS with a reason."
    )


def test_nav_does_not_reference_missing_pages() -> None:
    """The nav must not point at pages that do not exist."""
    missing = {
        page
        for page in _nav_referenced_pages()
        if not (DOCS_DIR / page).exists() and not page.startswith("http")
    }

    assert not missing, "mkdocs nav references non-existent pages: " + ", ".join(sorted(missing))


def test_allowlist_has_no_stale_entries() -> None:
    """Allowlisted pages must still exist and still be absent from the nav."""
    referenced = _nav_referenced_pages()
    for page, reason in ALLOWED_ORPHANS.items():
        assert (DOCS_DIR / page).exists(), f"allowlisted page {page!r} no longer exists"
        assert page not in referenced, (
            f"{page!r} is now in the nav - remove it from ALLOWED_ORPHANS (listed reason: {reason})"
        )
