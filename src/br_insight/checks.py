"""Built-site audits (Task 14): asset budgets + internal link checking.

``audit(out)`` walks a rendered tree and enforces the Global Constraints:

* gzip CSS payload of every stylesheet referenced by built pages ≤ 35 KB,
* gzip JS payload (``<script src>`` + static ES-module import chains) ≤ 25 KB,
* a search index, when present, stays ≤ 200 KB gzipped,
* every internal link/src/srcset referenced by built pages resolves to a
  real file; ``#fragment`` targets must match an id/name attribute where
  the target is readable HTML.

Returns ``(ok, report_lines)`` with a human-readable report for CLI use.
"""

from __future__ import annotations

import gzip
import re
from html.parser import HTMLParser
from pathlib import Path

BUDGET_CSS_GZ = 35 * 1024
BUDGET_JS_GZ = 25 * 1024
BUDGET_SEARCH_GZ = 200 * 1024

_SKIP_PREFIXES = ("http://", "https://", "//", "mailto:", "tel:", "data:")

_URL_ATTRS = {"href", "src", "srcset"}
_HTML_SUFFIX_RE = re.compile(r"\.html?$", re.I)
_ID_DECLARED_RE = re.compile(
    r"""(?:\bid\s*=\s*|\bname\s*=\s*)(['"])([^'"]+)\1""", re.I
)
_IMPORT_RE = re.compile(r"""\bfrom\s+["']([^"']+)["']""")
_SRCSET_ITEM_RE = re.compile(r"(\S+)\s+(?:[\d.]+w|\d+x)")


def _gz_len(data: bytes) -> int:
    return len(gzip.compress(data, compresslevel=9))


def _human(n: int) -> str:
    return f"{n:,} B"


class _RefCollector(HTMLParser):
    """Collect URL-ish attributes from built HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.refs: list[tuple[str, str]] = []  # (attr, raw value)

    def handle_starttag(self, tag, attrs) -> None:
        for name, value in attrs:
            if value and name.lower() in _URL_ATTRS:
                self.refs.append((name.lower(), value))


def _is_external(url: str) -> bool:
    return any(url.startswith(prefix) for prefix in _SKIP_PREFIXES)


def _urls_from_ref(attr: str, raw: str) -> list[str]:
    """Expand ``srcset`` candidates into individual URLs."""
    if attr != "srcset":
        return [raw]
    return [m.group(1) for m in _SRCSET_ITEM_RE.finditer(raw)]


def _split_url(url: str) -> tuple[Path | None, str]:
    """Return ``(path_part_or_None, fragment)``.

    ``None`` means the URL carries no path component (a pure ``#anchor``
    reference resolved against the referring page itself). Queries are
    stripped before filesystem resolution so filter chips like
    ``/library/?tag=x`` still map onto ``library/index.html``.
    """
    path_part, _, fragment = url.partition("#")
    path_part = path_part.split("?", 1)[0]
    return (Path(path_part) if path_part else None), fragment


def _resolve_target(page: Path, root: Path, url: str) -> Path | None:
    """Map a URL onto a filesystem path under ``root``; None when external."""
    if _is_external(url):
        return None
    path_part, _ = _split_url(url)
    if path_part is None:
        return None
    candidate = (
        root / path_part.relative_to(path_part.anchor)
        if path_part.is_absolute()
        else (page.parent / path_part)
    )
    candidate = candidate.resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None  # escapes the site tree — treat as external
    if candidate.suffix == "":  # directory-style link
        candidate = candidate / "index.html"
    return candidate


def _fragment_declared(target_html: Path, fragment: str) -> bool:
    """Cheap anchor rule: only consulted for readable HTML targets."""
    if not _HTML_SUFFIX_RE.search(str(target_html)):
        return True  # non-HTML targets: don't guess anchor semantics
    try:
        text = target_html.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    declared = {m.group(2).lower() for m in _ID_DECLARED_RE.finditer(text)}
    return fragment.lower() in declared


def collect_pages(root: Path) -> list[Path]:
    """Built HTML pages only.

    ``templates/`` (Jinja sources) is an authoring input that happens to
    live inside the tree; its unrendered ``{{ }}`` hrefs would false-fail
    the link check.
    """
    return sorted(
        p
        for p in root.rglob("*.html")
        if p.is_file() and "templates" not in p.relative_to(root).parts
    )


def _collect_refs(root: Path) -> tuple[list[tuple[Path, str, str]], bool]:
    """Raw ``(page, url, attr)`` triples across the tree; readable flag."""
    collector = _RefCollector()
    refs: list[tuple[Path, str, str]] = []
    all_pages_readable = True
    for page in collect_pages(root):
        try:
            collector.feed(page.read_text(encoding="utf-8"))
        except UnicodeDecodeError as exc:
            all_pages_readable = False
            refs.append((page, f"<unreadable: {exc}>", "href"))
            continue
        for attr, raw in collector.refs:
            for url in _urls_from_ref(attr, raw):
                refs.append((page, url, attr))
        collector.refs.clear()
    return refs, all_pages_readable


def _js_module_closure(entrypoints: set[Path], root: Path) -> set[Path]:
    """Expand ES-module import chains reachable from entrypoint scripts."""
    files = set(entrypoints)
    frontier = sorted(entrypoints)
    while frontier:
        module = frontier.pop()
        if not module.is_file():
            continue
        try:
            text = module.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for match in _IMPORT_RE.finditer(text):
            spec = match.group(1)
            if not spec.endswith(".js"):
                continue
            neighbor = (module.parent / spec).resolve()
            try:
                neighbor.relative_to(root)
            except ValueError:
                continue  # import escapes the site tree; not ours to budget
            if neighbor not in files:
                files.add(neighbor)
                frontier.append(neighbor)
    return files


def audit(out: Path) -> tuple[bool, list[str]]:
    """Run budgets + link checks against the rendered tree at ``out``."""
    ok = True
    report: list[str] = ["budgets:"]
    root = out.resolve()

    refs, _readable = _collect_refs(root)

    # -- asset collection for budgets -----------------------------------------
    css_files: set[Path] = set()
    js_entrypoints: set[Path] = set()
    for page, url, attr in refs:
        path_part, _fragment = _split_url(url)
        if path_part is None:
            continue
        suffix = path_part.suffix.lower()
        if attr == "href" and suffix == ".css":
            css_files.add(resolved := _resolve_target(page, root, url))
        elif attr == "src" and suffix == ".js":
            js_entrypoints.add(resolved := _resolve_target(page, root, url))
    js_files = _js_module_closure(js_entrypoints, root)

    def _sum_files(paths: set[Path]) -> int:
        total = 0
        for path in sorted(paths):
            if not path or not path.is_file():
                continue
            size = _gz_len(path.read_bytes())
            total += size
            shown = path.relative_to(root).as_posix()
            report.append(f"     {shown}: {_human(size)} gz")
        return total

    budgets = [
        (_sum_files(css_files), BUDGET_CSS_GZ, "CSS"),
        (_sum_files(js_files), BUDGET_JS_GZ, "JS"),
    ]
    search_indexes = sorted(p for p in root.rglob("search-index*") if p.is_file())
    if search_indexes:
        budgets.append(
            (
                sum(_gz_len(p.read_bytes()) for p in search_indexes),
                BUDGET_SEARCH_GZ,
                "search-index",
            )
        )
    else:
        report.append("     search-index: none present (skipped)")

    for total, limit, label in budgets:
        line = f"{label} gz total: {_human(total)} / limit {_human(limit)}"
        if total <= limit:
            report.append("PASS " + line)
        else:
            ok = False
            report.append(f"FAIL exceeds {line}")

    # -- internal link verification -------------------------------------------
    broken: list[str] = []
    checked: set[tuple[str, str]] = set()
    n_checked = 0
    for page, url, attr in refs:
        if url.startswith("<unreadable"):
            ok = False
            broken.append(f"{page.relative_to(root)}: {url}")
            continue
        if _is_external(url):
            continue
        path_part, fragment = _split_url(url)
        if path_part is None:
            target, base_url = page, url  # same-page anchor
        else:
            target = _resolve_target(page, root, url)
            base_url = url
            if target is None:
                continue  # off-site-relative URL: not ours to verify
        key = (base_url, str(target))
        if key in checked:
            continue
        checked.add(key)
        n_checked += 1
        if not target.exists():
            broken.append(
                f"{url} referenced from {page.relative_to(root)} → missing"
            )
        elif fragment and not _fragment_declared(target, fragment):
            broken.append(
                f"{url} referenced from {page.relative_to(root)} → no "
                f"id/name for #{fragment}"
            )

    report.append("")
    report.append(f"links: ({n_checked} unique internal references checked)")
    if broken:
        ok = False
        report.extend(f"FAIL {line}" for line in sorted(set(broken)))
    else:
        report.append("PASS all internal references resolve")

    report.insert(0, "check: PASS" if ok else "check: FAIL")
    return ok, report


def main_check(out: Path) -> int:
    """CLI wrapper used by :mod:`br_insight.cli`; prints report lines."""
    ok, report = audit(out)
    print("check: built-site audit (" + str(out) + ")")
    for line in report:
        print(line)
    return 0 if ok else 1
