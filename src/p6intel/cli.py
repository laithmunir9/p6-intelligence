from __future__ import annotations

import argparse
import json

from .normalize import normalize
from .parser import parse_xer
from .report import compare_files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="p6intel")
    subparsers = parser.add_subparsers(dest="command", required=True)
    parse_command = subparsers.add_parser("parse", help="parse an XER export")
    parse_command.add_argument("source")
    parse_command.add_argument("-o", "--output")
    compare_command = subparsers.add_parser("compare", help="compare two XER exports")
    compare_command.add_argument("before")
    compare_command.add_argument("after")
    compare_command.add_argument("-o", "--output")
    args = parser.parse_args(argv)
    if args.command == "compare":
        output_data = compare_files(args.before, args.after).model_dump_json(indent=2) + "\n"
    else:
        result = normalize(parse_xer(args.source)).model_dump(mode="json")
        output_data = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        with open(args.output, "w", encoding="utf-8") as stream:
            stream.write(output_data)
    else:
        print(output_data, end="")
    return 0
