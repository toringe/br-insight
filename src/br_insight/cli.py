"""Command-line interface for the br-insight static-site pipeline."""

import argparse
from pathlib import Path

from br_insight.checks import main_check
from br_insight.render import build


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``br-insight`` console script."""
    args = _parse_args(argv)
    return args.func(args)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="br-insight",
        description="Build pipeline for the br-insight static site.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser(
        "build", help="Render Markdown articles into the static site."
    )
    build.add_argument(
        "--out",
        default=".",
        help="Directory to write the rendered site into (default: repo root).",
    )
    build.set_defaults(func=_run_build)

    serve = subparsers.add_parser("serve", help="Serve the built site over HTTP.")
    serve.set_defaults(func=_run_serve)

    check = subparsers.add_parser(
        "check", help="Verify budgets and link integrity of the rendered site."
    )
    check.add_argument(
        "--out",
        default=".",
        help="Rendered site tree to audit (default: repo root).",
    )
    check.set_defaults(func=_run_check)

    return parser.parse_args(argv)


def _run_build(args: argparse.Namespace) -> int:
    written = build(root=Path.cwd(), out=Path(args.out))
    print(f"build: wrote {len(written)} page(s) into {args.out}")
    return 0


def _run_serve(args: argparse.Namespace) -> int:
    print("serve: serving the built site over HTTP (skeleton; not implemented yet)")
    return 0


def _run_check(args: argparse.Namespace) -> int:
    return main_check(Path(args.out))
