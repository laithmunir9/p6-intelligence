"""Deterministic, deduplicated registry for source-record evidence."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from p6intel.models.domain import SourceRecord
from .models import EvidenceRecord, EvidenceReference


class EvidenceRegistry:
    def __init__(self) -> None:
        self._records: dict[str, EvidenceRecord] = {}

    @staticmethod
    def _payload(side: str, record: EvidenceRecord) -> bytes:
        value = {"side": side, "table": record.table, "line_number": record.line_number,
                 "fields": record.fields, "values": record.values, "raw_line": record.raw_line}
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def register(self, side: str, record: SourceRecord | EvidenceRecord | dict[str, Any]) -> EvidenceReference:
        if side not in {"before", "after"}:
            raise ValueError("evidence side must be 'before' or 'after'")
        if isinstance(record, SourceRecord):
            evidence = EvidenceRecord(side=side, table=record.table, line_number=record.line_number,
                                      fields=record.fields, values=record.values, raw_line=record.raw_line)
        elif isinstance(record, EvidenceRecord):
            evidence = record.model_copy(update={"side": side})
        else:
            evidence = EvidenceRecord.model_validate({**record, "side": side})
        digest = hashlib.sha256(self._payload(side, evidence)).hexdigest()[:12]
        evidence_id = f"ev_{digest}"
        self._records.setdefault(evidence_id, evidence)
        return EvidenceReference(evidence_id=evidence_id)

    def resolve(self, reference: EvidenceReference | str) -> EvidenceRecord:
        evidence_id = reference.evidence_id if isinstance(reference, EvidenceReference) else reference
        try:
            return self._records[evidence_id]
        except KeyError as exc:
            raise KeyError(f"unknown evidence ID: {evidence_id}") from exc

    def model_dump(self) -> dict[str, EvidenceRecord]:
        return dict(self._records)

    def __len__(self) -> int:
        return len(self._records)
