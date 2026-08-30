from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import subprocess
import sys

from sqlalchemy import select, text

from app.models.platform import DatasetVersion
from app.reporting.semantic_service import ReportReconciliationValidator, ReportSemanticService
from app.reporting.view_definitions import CANONICAL_VIEWS


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parent


class DatasetFinalizationError(RuntimeError):
    pass


@dataclass(frozen=True)
class DatasetFinalizationResult:
    dataset_version_id: object
    dataset_version_name: str
    status: str
    business_content_hash: str
    report_semantic_content_hash: str
    reused: bool


class DatasetFinalizationService:
    def __init__(self, session, *, require_repository_scan=True):
        self.session = session
        self.require_repository_scan = require_repository_scan

    def _platform_tables(self):
        return list(self.session.scalars(text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='platform' "
            "AND table_type='BASE TABLE' AND table_name<>'dataset_versions' ORDER BY table_name"
        )))

    def _validate_prerequisites(self, dataset_id):
        tables = self._platform_tables()
        if not tables:
            raise DatasetFinalizationError("INCOMPLETE_MASTER_WORLD")
        for table_name in tables:
            count = self.session.scalar(text(f'SELECT count(*) FROM platform."{table_name}" WHERE dataset_version_id=:did'), {"did": dataset_id})
            if not count:
                raise DatasetFinalizationError(f"INCOMPLETE_PLATFORM_STAGE:{table_name}")
        private_count = self.session.scalar(text(
            "SELECT count(*) FROM evaluation.scenario_truth WHERE dataset_version_id=:did"
        ), {"did": dataset_id})
        if not private_count:
            raise DatasetFinalizationError("INCOMPLETE_SCENARIO_WORLD")
        for view in CANONICAL_VIEWS:
            self.session.execute(text(f"SELECT 1 FROM reporting.{view} WHERE dataset_version_id=:did LIMIT 1"), {"did": dataset_id})
        ReportReconciliationValidator(self.session).validate(dataset_id)
        if self.require_repository_scan:
            result = subprocess.run(
                [sys.executable, str(REPOSITORY_ROOT / "scripts" / "check_forbidden_terms.py")],
                cwd=REPOSITORY_ROOT, capture_output=True, text=True, check=False,
            )
            if result.returncode:
                raise DatasetFinalizationError("FORBIDDEN_TERM_SCAN_FAILED")

    def _business_hash(self, dataset):
        digest = sha256()
        digest.update(b"system-a-business-content-v1\0")
        digest.update(dataset.generation_signature.encode())
        digest.update(b"\0")
        for table_name in self._platform_tables():
            digest.update(table_name.encode())
            digest.update(b"\0")
            rows = self.session.scalars(text(
                f"SELECT (to_jsonb(t)-'created_at'-'generated_at')::text payload FROM platform.\"{table_name}\" t "
                "WHERE dataset_version_id=:did ORDER BY payload"
            ), {"did": dataset.dataset_version_id})
            for payload in rows:
                digest.update(payload.encode())
                digest.update(b"\n")
        semantic_hash = ReportSemanticService(self.session).summary(dataset.dataset_version_id)["report_semantic_content_hash"]
        digest.update(b"report-semantic\0")
        digest.update(semantic_hash.encode())
        return digest.hexdigest(), semantic_hash

    def finalize(self, dataset_id):
        with self.session.begin():
            dataset = self.session.scalar(select(DatasetVersion).where(
                DatasetVersion.dataset_version_id == dataset_id).with_for_update())
            if dataset is None:
                raise DatasetFinalizationError("DATASET_NOT_FOUND")
            if dataset.status not in {"GENERATING", "READY"}:
                raise DatasetFinalizationError("DATASET_NOT_FINALIZABLE")
            self._validate_prerequisites(dataset_id)
            content_hash, semantic_hash = self._business_hash(dataset)
            if dataset.status == "READY":
                if dataset.business_content_hash != content_hash:
                    raise DatasetFinalizationError("READY_DATASET_CONTENT_MISMATCH")
                return DatasetFinalizationResult(dataset_id, dataset.version_name, "READY", content_hash, semantic_hash, True)
            if dataset.business_content_hash is not None:
                raise DatasetFinalizationError("GENERATING_DATASET_HAS_FINAL_HASH")
            dataset.business_content_hash = content_hash
            dataset.status = "READY"
            self.session.flush()
            return DatasetFinalizationResult(dataset_id, dataset.version_name, "READY", content_hash, semantic_hash, False)

