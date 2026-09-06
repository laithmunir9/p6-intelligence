from __future__ import annotations

import argparse
import json

from .normalize import normalize
from .parser import parse_xer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="p6intel")
    subparsers = parser.add_subparsers(dest="command", required=True)
    parse_command = subparsers.add_parser("parse", help="parse an XER export")
    parse_command.add_argument("source")
    parse_command.add_argument("-o", "--output")
    args = parser.parse_args(argv)
    result = normalize(parse_xer(args.source)).model_dump(mode="json")
    output = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        with open(args.output, "w", encoding="utf-8") as stream:
            stream.write(output)
    else:
        print(output, end="")
    return 0
