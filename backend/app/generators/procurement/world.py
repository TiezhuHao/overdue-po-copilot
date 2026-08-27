from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.inspection import inspect

from app.generators.signature import canonical_json, content_hash
from app.models.platform import PoHeader, PoLine, PoLineSchedule


@dataclass
class ProcurementWorld:
    po_headers: list[PoHeader] = field(default_factory=list)
    po_lines: list[PoLine] = field(default_factory=list)
    po_line_schedules: list[PoLineSchedule] = field(default_factory=list)

    COLLECTION_NAMES = ("po_headers", "po_lines", "po_line_schedules")

    def all_records(self) -> list[Any]:
        return [row for name in self.COLLECTION_NAMES for row in getattr(self, name)]

    def counts(self) -> dict[str, int]:
        return {name: len(getattr(self, name)) for name in self.COLLECTION_NAMES}

    @staticmethod
    def _record_payload(record: Any) -> dict[str, Any]:
        mapper = inspect(type(record))
        return {
            column.key: getattr(record, column.key)
            for column in mapper.columns
            if column.key != "created_at"
        }

    def procurement_content_hash(self, procurement_signature: str) -> str:
        payload = self._content_payload()
        payload["procurement_signature"] = procurement_signature
        return content_hash(payload)

    def procurement_facts_hash(self) -> str:
        return content_hash(self._content_payload())

    def _content_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for name in self.COLLECTION_NAMES:
            rows = [self._record_payload(record) for record in getattr(self, name)]
            payload[name] = sorted(rows, key=canonical_json)
        return payload
