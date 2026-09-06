"""Small, deliberately conservative parser for P6's tab-separated XER format."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class XERDiagnostic:
    line_number: int
    message: str
    raw_line: str


@dataclass
class RawRecord:
    """Lossless record evidence retained alongside the normalized mapping."""

    fields: list[str]
    values: list[str]
    line_number: int
    raw_line: str


@dataclass
class TableData:
    name: str
    fields: list[str] = field(default_factory=list)
    records: list[dict[str, str | None]] = field(default_factory=list)
    raw_records: list[RawRecord] = field(default_factory=list)


@dataclass
class ParsedXER:
    tables: dict[str, TableData]
    diagnostics: list[XERDiagnostic] = field(default_factory=list)

    @property
    def unknown_tables(self) -> dict[str, TableData]:
        supported = {"PROJECT", "PROJWBS", "TASK", "TASKPRED", "CALENDAR"}
        return {key: value for key, value in self.tables.items() if key not in supported}


class XERParser:
    """Parse XER control records while retaining data that this prototype ignores."""

    def parse_text(self, text: str) -> ParsedXER:
        tables: dict[str, TableData] = {}
        diagnostics: list[XERDiagnostic] = []
        current: TableData | None = None

        for line_number, raw in enumerate(text.splitlines(), 1):
            line = raw.rstrip("\r")
            if not line:
                continue
            parts = line.split("\t")
            marker = parts[0].lstrip("\ufeff")
            if marker == "%T":
                if len(parts) != 2 or not parts[1].strip():
                    diagnostics.append(XERDiagnostic(line_number, "malformed table declaration", line))
                    current = None
                    continue
                name = parts[1].strip().upper()
                current = TableData(name=name)
                tables[name] = current
            elif marker == "%F":
                if current is None:
                    diagnostics.append(XERDiagnostic(line_number, "field declaration without table", line))
                    continue
                if len(parts) < 2:
                    diagnostics.append(XERDiagnostic(line_number, "malformed field declaration", line))
                    continue
                current.fields = parts[1:]
            elif marker == "%R":
                if current is None or not current.fields:
                    diagnostics.append(XERDiagnostic(line_number, "record without table fields", line))
                    continue
                values = parts[1:]
                if len(values) > len(current.fields):
                    diagnostics.append(XERDiagnostic(line_number, "record has more values than declared fields", line))
                record = {
                    name: (values[index] if index < len(values) and values[index] != "" else None)
                    for index, name in enumerate(current.fields)
                }
                if len(values) < len(current.fields):
                    diagnostics.append(XERDiagnostic(line_number, "record has fewer values than declared fields", line))
                if len(values) > len(current.fields):
                    record["__extra__"] = "\t".join(values[len(current.fields):])
                current.records.append(record)
                current.raw_records.append(RawRecord(fields=list(current.fields), values=list(values),
                                                     line_number=line_number, raw_line=line))
            elif marker == "%E":
                current = None
            elif marker.startswith("%"):
                diagnostics.append(XERDiagnostic(line_number, f"unknown control record {marker}", line))
            else:
                diagnostics.append(XERDiagnostic(line_number, "malformed non-XER record", line))
        return ParsedXER(tables=tables, diagnostics=diagnostics)

    def parse_bytes(self, data: bytes) -> ParsedXER:
        # XER exports are commonly UTF-8, but Windows exports may carry a legacy code page.
        for encoding in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                return self.parse_text(data.decode(encoding))
            except UnicodeDecodeError:
                continue
        raise UnicodeDecodeError("utf-8", data, 0, len(data), "unable to decode XER bytes")

    def parse_file(self, path: str | Path) -> ParsedXER:
        return self.parse_bytes(Path(path).read_bytes())


def parse_xer(source: str | bytes | Path) -> ParsedXER:
    parser = XERParser()
    if isinstance(source, bytes):
        return parser.parse_bytes(source)
    if isinstance(source, Path):
        return parser.parse_file(source)
    if isinstance(source, str) and "\n" not in source:
        try:
            if Path(source).is_file():
                return parser.parse_file(source)
        except OSError:
            pass
    return parser.parse_text(str(source))
