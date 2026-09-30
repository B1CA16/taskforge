"""Check that links in the repository's Markdown files point somewhere real.

Checks relative links (`[text](../other.md)`), their `#anchors`, and absolute
links to this repository's `main` branch (used by README and CHANGELOG, which are
also rendered on PyPI). External URLs are not fetched.

Usage:
    python scripts/check_links.py

Exits with status 1 if any link is broken.
"""

import re
import subprocess
import sys
from pathlib import Path

REPO_URL_PREFIX = "https://github.com/B1CA16/taskforge/blob/main/"
ROOT = Path(__file__).resolve().parent.parent

_FENCED_CODE = re.compile(r"^(`{3,}).*?^\1", re.MULTILINE | re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_LINK = re.compile(r"\]\(([^)\s]+)\)")
_HEADING = re.compile(r"^#{1,6} +(.+?)\s*$", re.MULTILINE)


def markdown_files() -> list[Path]:
    """Return tracked and untracked (but not ignored) Markdown files."""
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.md"],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    ).stdout.split()
    return [ROOT / name for name in listed if (ROOT / name).exists()]


def strip_code(text: str) -> str:
    """Remove code blocks and spans, where link-like text isn't a link."""
    return _INLINE_CODE.sub("", _FENCED_CODE.sub("", text))


def heading_anchors(path: Path) -> set[str]:
    """Return the anchors GitHub generates for the headings in `path`."""
    text = _FENCED_CODE.sub("", path.read_text(encoding="utf-8"))
    anchors = set()
    for heading in _HEADING.findall(text):
        # GitHub: lowercase, drop punctuation except hyphens, spaces become hyphens.
        anchor = re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")
        anchors.add(anchor)
    return anchors


def check_link(source: Path, target: str) -> str | None:
    """Return a description of the problem with `target`, or None if it's fine."""
    if target.startswith(REPO_URL_PREFIX):
        target = target.removeprefix(REPO_URL_PREFIX)
        base = ROOT
    elif re.match(r"[a-z][a-z0-9+.-]*:", target) or target.startswith("<"):
        return None  # external URL, mailto:, or a placeholder like <job_id>
    else:
        base = source.parent

    path_part, _, anchor = target.partition("#")
    resolved = (base / path_part).resolve() if path_part else source
    if not resolved.exists():
        return "file not found"
    if anchor and resolved.suffix == ".md" and anchor not in heading_anchors(resolved):
        return f"no heading for #{anchor}"
    return None


def main() -> int:
    """Check every Markdown file and report broken links."""
    broken = 0
    for path in markdown_files():
        for target in _LINK.findall(strip_code(path.read_text(encoding="utf-8"))):
            problem = check_link(path, target)
            if problem:
                broken += 1
                print(f"{path.relative_to(ROOT)}: {target} ({problem})")
    print(f"{broken} broken link(s)" if broken else "All links OK")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
