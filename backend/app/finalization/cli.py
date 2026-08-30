import argparse
import json

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.finalization.service import DatasetFinalizationError, DatasetFinalizationService
from app.models.platform import DatasetVersion


def main():
    parser = argparse.ArgumentParser(description="Finalize one complete synthetic System A dataset")
    parser.add_argument("--dataset-version-name", required=True)
    args = parser.parse_args()
    # Publication validates cross-schema views and updates dataset status; run it
    # with the owner boundary rather than the write-only generator role.
    engine = create_engine(settings.database_url_owner.get_secret_value(), hide_parameters=True, pool_pre_ping=True)
    try:
        with Session(engine, expire_on_commit=False) as session:
            dataset_id = session.scalar(select(DatasetVersion.dataset_version_id).where(
                DatasetVersion.version_name == args.dataset_version_name))
            if dataset_id is None:
                raise DatasetFinalizationError("DATASET_NOT_FOUND")
            session.rollback()
            result = DatasetFinalizationService(session).finalize(dataset_id)
            print(json.dumps({
                "dataset_version_id": str(result.dataset_version_id),
                "dataset_version_name": result.dataset_version_name,
                "status": result.status,
                "business_content_hash": result.business_content_hash,
                "report_semantic_content_hash": result.report_semantic_content_hash,
                "reused": result.reused,
            }, sort_keys=True))
    except Exception as exc:
        raise SystemExit(exc.__class__.__name__) from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
