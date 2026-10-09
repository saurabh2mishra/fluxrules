"""Fix two formatting issues across all docs/ markdown files:
1. Inline bullet lists -> proper multiline markdown lists
2. Em dashes (—) -> simple hyphens (-)
"""
import re
import pathlib

docs_dir = pathlib.Path("/Users/saurabhmishra/projects/fluxrules/docs")


def fix_em_dashes(text):
    text = text.replace(" — ", " - ")
    text = text.replace("— ", "- ")
    text = text.replace(" —", " -")
    text = text.replace("—", "-")
    return text


def fix_inline_lists(text):
    """Convert lines like 'Intro text: - item1 - item2 - item3' to multiline lists."""
    lines = text.split("\n")
    out = []
    for line in lines:
        # Skip lines that are already a single list item (start with - or *)
        stripped = line.lstrip()
        if stripped.startswith("- ") or stripped.startswith("* "):
            out.append(line)
            continue

        # Match: text ending with colon/colon+space, then "- item - item" (2+ items inline)
        m = re.match(r'^(\s*)(.+?:)\s+-\s+(.+)$', line)
        if m:
            indent = m.group(1)
            intro = m.group(2)
            rest = m.group(3)
            # Count how many "- " separators exist in rest
            # Split on " - " boundaries that look like list item separators
            # Use a pattern that splits on " - " preceded by word chars
            parts = re.split(r'\s+-\s+', rest)
            if len(parts) >= 2:
                # It's a genuine inline list
                out.append(indent + intro)
                out.append("")
                for part in parts:
                    part = part.strip()
                    if part:
                        out.append(indent + "- " + part)
                continue

        out.append(line)
    return "\n".join(out)


changed = []
for md_file in sorted(docs_dir.rglob("*.md")):
    original = md_file.read_text(encoding="utf-8")
    fixed = fix_em_dashes(original)
    fixed = fix_inline_lists(fixed)
    if fixed != original:
        md_file.write_text(fixed, encoding="utf-8")
        changed.append(md_file.name)
        print(f"Fixed: {md_file.name}")

print(f"\nTotal files changed: {len(changed)}")
