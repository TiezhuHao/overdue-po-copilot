"""One explicitly requested correction; no public API or automatic reset."""

import argparse
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import create_database_engine
from app.generators.evidence_foundation.cli import summary
from app.models.platform import DatasetVersion
from app.services.evidence_timing_correction import EvidenceTimingCorrectionService


def main():
    parser = argparse.ArgumentParser(description='Correct audited GENERATING demo evidence timing')
    parser.add_argument('--expected-old-hash', required=True)
    parser.add_argument('--summary-output', type=Path)
    args = parser.parse_args()
    engine = create_database_engine(settings.database_url_generator.get_secret_value())
    try:
        with Session(engine, expire_on_commit=False) as session:
            dataset_id = session.scalar(select(DatasetVersion.dataset_version_id).where(DatasetVersion.version_name == 'demo-master-v1'))
            session.rollback()
            result = EvidenceTimingCorrectionService(session).correct(dataset_id, args.expected_old_hash)
            rendered = json.dumps(summary(result), ensure_ascii=False, indent=2, sort_keys=True)
        if args.summary_output:
            args.summary_output.write_text(rendered + '\n', encoding='utf-8')
        print(rendered)
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
