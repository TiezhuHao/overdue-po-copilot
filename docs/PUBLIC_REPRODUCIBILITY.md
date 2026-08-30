# System A — public Excel reproducibility checkpoint

Synthetic data only. Scope: replace the Excel writer, not business features.
Pre-fix commit: `bb0876d`. System B remains NOT STARTED. No LICENSE was added.

## Root cause and dependency audit

The previous Python exporter launched a Node bridge whose workbook dependency was
`@oai/artifact-tool`, unavailable as an ordinary public npm dependency. A local
authorized installation did not make that path reproducible for GitHub users.

| Class | Location | Resolution |
|---|---|---|
| A — production | Python exporter's Node discovery, environment settings and subprocess bridge | Removed; workbook creation now directly uses `openpyxl==3.1.5` |
| A — production | `backend/app/reporting/xlsx_runtime.mjs` and its `package.json` | Deleted; no private package copied or redistributed |
| B — historical documentation | `FINAL_REVIEW.md`, FR-02, and this checkpoint's root-cause description | Retained as historical evidence, with an explicit superseding notice |
| C — test-only | Integration test removes former Node environment variables and clears PATH | Proves export works without that runtime; does not load it |

System A installs from `backend/requirements.txt`; its Dockerfile uses the same
file. There is no separate Python project/lock dependency manifest. The remaining
frontend `package.json`, pnpm lockfile and Dockerfile belong to the initial unused
placeholder, not the System A runtime; they were not expanded or changed.
README and LOCAL_SETUP no longer require private tooling for export or validation.

## Preserved architecture and contract

Canonical reporting views → existing Report Header Manifest → Python Excel writer.
Queries, pivot preparation, version selection and dynamic header preparation are
unchanged. No business formula moved into the writer. Report Header Manifest,
Field Mapping, API, generators, finalization, models and migrations are unchanged.

| Report | Exact columns | Dynamic contract |
|---|---:|---|
| 1 | 37 | Static |
| 2 | 106 | Static |
| 3 | 23 | Seven months starting in each Forecast Version's month; one sheet per version |
| 4 | 44 | Thirteen Monday-start weeks from Dataset snapshot |
| 5 | 22 | Static |
| 6 | 60 | Six natural months after the selected Stockpile Version month |

The writer preserves merged/multi-row headers, ordered body values, comma-joined
array display, null/blank cells and numeric zero. Dates and timestamps remain
native Excel cells; timezone-aware timestamps use the previous writer's UTC
display value, because Excel does not have a timezone-aware cell type.
It adds basic header styling,
freeze panes, filters, bounded column widths and date/numeric formats. Text remains
literal, including formula-like source text. No diagnostic answers or unconfirmed
auxiliary formulas are invented. Binary xlsx timestamp equality is not required;
business values and row/header ordering must match across repeated exports.

## Verification

**Final full-suite run in the fresh public-dependency venv: 471 passed, 0 failed,
0 skipped, 844.98 seconds (14:04).** One existing Starlette/httpx deprecation
warning remains. This single run tests the final writer implementation and
supersedes the intermediate run below; it is not a sum of separate test runs.

Final direct openpyxl targeted tests in the clean venv: **60 passed, 0 failed,
0 skipped** (76.80 seconds), including Excel writer, six-report integration and
report API regression. The existing Starlette/httpx warning is unrelated to the
writer. The earlier implementation's targeted run was 57 passed (61.63 seconds),
before adding the three native date/timestamp cases described below.

The tests reopen every workbook with `load_workbook`, compare all cells against
canonical-view-derived payloads, reconcile Report 3 pivot totals independently
against SQL, compare repeat exports and validate exact headers, row counts,
dynamic dates, blank fields, formatting, and absence of formulas/error cells or
forbidden terms. No private workbook tool participates in export or validation.

Initial full-suite run in the backend venv: **468 passed, 0 failed, 0 skipped**,
585.27 seconds, one existing Starlette/httpx deprecation warning. This includes
disposable-database downgrade/upgrade, real-role permissions, API/OpenAPI,
finalization, determinism, Excel and repository hygiene. This is a fresh full run,
not a sum of targeted runs. A subsequent historical-workbook comparison caught
timestamp text-vs-native-cell representation; the writer was corrected and three
native date/timestamp regression cases were added. The final 471-test result above
includes that correction and supersedes this intermediate 468-test run.

### Clean public environment

A new Python 3.12 venv with `include-system-site-packages = false` installed all
requirements using `pip --isolated install --no-cache-dir --index-url https://pypi.org/simple`.
The pip install report contains **41 packages**, all downloaded over HTTPS from
`files.pythonhosted.org` with SHA256 metadata. `pip check` returned no broken requirements.
No cached/private package or inherited site-packages supplied the workbook engine.

The unchanged CLI exported all six reports twice under this fresh interpreter,
with PATH empty and both old Node variables absent. All twelve files reopened in
openpyxl. The final files matched canonical payloads, repeat-export content and
the historical six-report smoke files in business values and ordering, including
native timestamps. Full header-cell/merge checks included parent and dynamic headers.

| Report | Data rows | Sheets | Body cells checked | Numeric zero cells | Blank cells |
|---|---:|---:|---:|---:|---:|
| 1 | 115 | 1 | 4,255 | 69 | 536 |
| 2 | 60 | 1 | 6,360 | 566 | 3,180 |
| 3 | 900 | 28 | 20,700 | 1,808 | 900 |
| 4 | 60 | 1 | 2,640 | 155 | 516 |
| 5 | 272 | 1 | 5,984 | 0 | 272 |
| 6 | 24 | 1 | 1,440 | 54 | 819 |

Numeric zero counts exclude boolean false cells. No formula/error cells were present.
Floating-point roundtrips use the established
strict numerical tolerance; null and numeric zero remain distinct. This proves a
fresh public Python dependency environment against the existing local PostgreSQL,
not a newly provisioned operating system or a rebuilt development Dataset.

## Reproduction procedure

Use the commands in [LOCAL_SETUP — Clean-environment smoke](LOCAL_SETUP.md#clean-environment-smoke).
They create a fresh venv, install all Python requirements from public PyPI without
the download cache, run `pip check`, and invoke the existing export CLI twice to
produce six workbooks in each output directory. PostgreSQL and a READY synthetic
Dataset must already exist; setup documents the complete new-database workflow.

The smoke procedure only reads the READY Dataset. Disposable database regression
tests are separate; never point them at the development database. Local venvs,
install reports, generated workbooks and credentials are ignored by Git.

## Protected baseline

Dataset: `demo-master-v1`, status `READY`.

- Business content hash: `f91717e3af70a518caf31673fd5f733f1e12b2dfb9598b1e7c0cec20c36ac199`.
- Report semantic hash: `c9628312839ac5c5ca0f51e6c1694897e05bfaece70e9ee6282f6f02cee579d9`.
- Private truth aggregate fingerprint: `62e72a5437da1f1c4b699c757d693ae4` (aggregate only; no row-level answers published).

Read-only recomputation after the full regression matched all three pre-fix
values, and Dataset status remains READY. The development business world was not
regenerated or finalized; disposable test-database changes are separate.

## Changed files

- `backend/app/reporting/excel_export.py`: public workbook writer only.
- `backend/requirements.txt`: pin openpyxl.
- `backend/tests/test_report_excel_integration.py`: direct public-library validation.
- `backend/tests/test_excel_writer.py`: literal-text safety regression tests.
- Deleted `backend/app/reporting/xlsx_runtime.mjs` and `backend/app/reporting/package.json`.
- `README.md`, `docs/LOCAL_SETUP.md`, `docs/FINAL_REVIEW.md`, and this checkpoint:
  public setup, current evidence, and explicit historical boundaries.

## Publication checks

The forbidden-term scanner passed across 188 files. Repository hygiene checks
found no known local credentials or absolute local paths in publishable files,
no per-record hidden truth in examples, and no tracked runtime data. A separate
common-token/private-key pattern scan also found no matches. These are scoped
automated checks, not a guarantee that no conceivable secret could exist.
`git diff --check` passed. Generated workbooks, the install report and clean venv
remain under ignored `exports/`; no runtime assets are added to Git.

## License boundary

`LICENSE_MISSING` remains for the maintainer to decide. Public dependency/runtime
reproducibility does not grant a license to the repository's code. This checkpoint
does not claim production authentication, deployment hardening, or System B work.

Final technical status: **System A COMPLETE; public runtime REPRODUCIBLE;
GitHub portfolio technical readiness READY; System B NOT STARTED.**
No remaining public-runtime blocker was found. `LICENSE_MISSING` is still a
maintainer decision, not silently resolved by this technical checkpoint.
