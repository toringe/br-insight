"""Command-line interface for the br-insight static-site pipeline."""

import argparse


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
        "check", help="Verify links and integrity of the rendered site."
    )
    check.set_defaults(func=_run_check)

    return parser.parse_args(argv)


def _run_build(args: argparse.Namespace) -> int:
    print(f"build: rendering site into {args.out} (skeleton; not implemented yet)")
    return 0


def _run_serve(args: argparse.Namespace) -> int:
    print("serve: serving the built site over HTTP (skeleton; not implemented yet)")
    return 0


def _run_check(args: argparse.Namespace) -> int:
    print("check: running link and integrity checks (skeleton; not implemented yet)")
    return 0
