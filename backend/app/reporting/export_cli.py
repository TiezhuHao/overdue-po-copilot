import argparse
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.reporting.excel_export import REPORT_FILENAMES, ReportExcelExporter


def main():
    parser = argparse.ArgumentParser(description="Export canonical System A reports to xlsx")
    parser.add_argument("--dataset-version-name", required=True)
    parser.add_argument("--report", choices=["all", "report1", "report2", "report3", "report4", "report5", "report6"], default="all")
    parser.add_argument("--output-dir", default="../exports")
    args = parser.parse_args()
    selected = range(1, 7) if args.report == "all" else [int(args.report.removeprefix("report"))]
    engine = create_engine(settings.database_url_api.get_secret_value(), hide_parameters=True, pool_pre_ping=True)
    try:
        with Session(engine) as session:
            exporter = ReportExcelExporter(session)
            results = [exporter.export(report_id, args.dataset_version_name, args.output_dir) for report_id in selected]
            print(json.dumps([{"report": f"report{r.report_id}", "file": REPORT_FILENAMES[r.report_id],
                               "rows": r.row_count, "sheets": r.sheet_count} for r in results], sort_keys=True))
    except Exception as exc:
        raise SystemExit(exc.__class__.__name__) from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
