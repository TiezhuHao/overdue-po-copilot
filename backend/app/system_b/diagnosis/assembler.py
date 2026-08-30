"""Join and trace canonical evidence; metric arithmetic stays in Analytics."""
from app.system_b.analytics.calculations import (
    calculate_coverage, calculate_forecast_change, calculate_po_aging,
    calculate_po_consumption, calculate_supply_demand,
)
from app.system_b.diagnosis.models import (
    AnalyticsEvidence, EntityKey, EvidenceBundle, EvidenceFact, EvidenceInputs,
    EvidenceKind as K, MissingCode as M, MissingEvidence,
)


class EvidenceAssemblyError(ValueError):
    """Stable validation code only; never include source objects or credentials."""


def entity_keys(row):
    names = (
        "po_header_id", "po_line_id", "po_line_schedule_id", "material_id", "organization_id",
        "supplier_id", "po_reference_project_id", "project_id", "forecast_version_id",
        "weekly_forecast_snapshot_id", "source_forecast_version_id", "product_config_id",
        "supply_demand_snapshot_id", "inventory_snapshot_id", "stockpile_version_id", "stockpile_record_id",
    )
    return tuple(EntityKey(name=name, value=getattr(row, name)) for name in names if getattr(row, name, None) is not None)


def _check_inputs(inputs):
    po = inputs.po
    rows = (inputs.weekly, inputs.supply, inputs.previous_forecast, inputs.current_forecast, *inputs.products)
    if inputs.stockpile is not None:
        query = inputs.stockpile
        if query.material_id != po.material_id:
            raise EvidenceAssemblyError("STOCKPILE_QUERY_MATERIAL_MISMATCH")
        if query.as_of_date != po.order_date or query.requested_version_id is not None:
            raise EvidenceAssemblyError("STOCKPILE_QUERY_NOT_ORDER_DATE_SELECTION")
        if query.page.dataset_version_id != po.dataset_version_id or query.page.snapshot_date != po.snapshot_date:
            raise EvidenceAssemblyError("STOCKPILE_PAGE_SCOPE_MISMATCH")
        selection = query.page.stockpile_selection
        if selection is not None:
            if selection.as_of_date != po.order_date or selection.as_of_date > po.snapshot_date:
                raise EvidenceAssemblyError("STOCKPILE_SELECTION_TIME_MISMATCH")
            values = (selection.stockpile_version_id, selection.stockpile_version_date, selection.sequence_no)
            if any(value is None for value in values) and not all(value is None for value in values):
                raise EvidenceAssemblyError("INCOMPLETE_VERSION_METADATA")
            if selection.stockpile_version_date is not None and selection.stockpile_version_date > po.order_date:
                raise EvidenceAssemblyError("FUTURE_STOCKPILE_VERSION")
            if selection.stockpile_version_id is None and query.page.total != 0:
                raise EvidenceAssemblyError("STOCKPILE_ROWS_WITHOUT_VERSION")
            for row in query.page.items:
                if (row.stockpile_version_id, row.stockpile_version_date, row.stockpile_version_sequence) != values:
                    raise EvidenceAssemblyError("STOCKPILE_ROW_VERSION_MISMATCH")
        if len(query.page.items) > query.page.total:
            raise EvidenceAssemblyError("INCONSISTENT_STOCKPILE_COUNT")
        if query.page.total > 1:
            raise EvidenceAssemblyError("STOCKPILE_GRAIN_MISMATCH")
        rows += query.page.items
    for row in rows:
        if row is None:
            continue
        if row.dataset_version_id != po.dataset_version_id:
            raise EvidenceAssemblyError("DATASET_MISMATCH")
        if row.snapshot_date != po.snapshot_date:
            raise EvidenceAssemblyError("SNAPSHOT_MISMATCH")
        if row.material_id is None or po.material_id is None:
            raise EvidenceAssemblyError("MISSING_MATERIAL_JOIN_ID")
        if row.material_id != po.material_id:
            raise EvidenceAssemblyError("MATERIAL_MISMATCH")
        organization = getattr(row, "organization_id", None)
        if organization is not None and po.organization_id is not None and organization != po.organization_id:
            raise EvidenceAssemblyError("ORGANIZATION_MISMATCH")
        schedule = getattr(row, "po_line_schedule_id", None)
        if schedule is not None and po.po_line_schedule_id is not None and schedule != po.po_line_schedule_id:
            raise EvidenceAssemblyError("SCHEDULE_MISMATCH")
        for name in ("forecast_version_date", "forecast_snapshot_date", "supply_snapshot_date", "inventory_snapshot_date"):
            value = getattr(row, name, None)
            if value is not None and value > po.snapshot_date:
                raise EvidenceAssemblyError("FUTURE_OBSERVATION")
    config_keys = [(p.project_id, p.product_config_id) for p in inputs.products]
    if len(config_keys) != len(set(config_keys)):
        raise EvidenceAssemblyError("DUPLICATE_CONFIGURATION")


def assemble_evidence(inputs: EvidenceInputs) -> EvidenceBundle:
    # Revalidate even model_copy/construct inputs; preserve only canonical fields.
    inputs = EvidenceInputs.model_validate(inputs.model_dump())
    _check_inputs(inputs)
    po, weekly, supply = inputs.po, inputs.weekly, inputs.supply
    previous, current = inputs.previous_forecast, inputs.current_forecast
    metrics = AnalyticsEvidence(
        aging=calculate_po_aging(po.order_date, po.material_lt_days, as_of_date=po.snapshot_date),
        consumption=calculate_po_consumption(po, weekly),
        coverage=calculate_coverage(weekly.good_subinventory_qty if weekly else None, weekly.weeks if weekly else None),
        supply_demand=calculate_supply_demand(supply),
        forecast_change=calculate_forecast_change(previous, current),
    )
    facts = []
    missing = {kind: MissingEvidence(kind=kind, code=M.NOT_PROVIDED) for kind in K}
    missing[K.HISTORICAL_LIFECYCLE] = MissingEvidence(kind=K.HISTORICAL_LIFECYCLE, code=M.HISTORICAL_LIFECYCLE_UNAVAILABLE)

    def emit(prefix, kind, source, row, fields, *, derived=(), observed_on=None, version_date=None,
             sequence=None, period=None, keys=None):
        for field, value in fields.items():
            facts.append(EvidenceFact(
                evidence_id=f"{prefix}.{field}", kind=kind, source=source,
                entity_keys=entity_keys(row) if keys is None else keys,
                dataset_version_id=po.dataset_version_id, snapshot_date=po.snapshot_date,
                observed_on=observed_on or po.snapshot_date, version_date=version_date,
                version_sequence=sequence, period=period, field=field, observed_value=value, derived_from=derived,
            ))

    def ready(kind):
        missing.pop(kind, None)

    def require_ids(kind, row, names):
        absent = tuple(name for name in names if getattr(row, name, None) is None)
        if absent:
            missing[kind] = MissingEvidence(kind=kind, code=M.MISSING_STABLE_ID, fields=absent)
        return not absent

    def numeric(kind, prefix, metric, fields, parents, dependencies):
        if any(key in missing for key in dependencies):
            missing[kind] = MissingEvidence(kind=kind, code=M.MISSING_REQUIRED_FIELD,
                                            fields=tuple(key.value for key in dependencies if key in missing))
            return
        if any(getattr(metric, field) is None for field in fields):
            missing[kind] = MissingEvidence(kind=kind, code=M.NOT_COMPUTABLE,
                                            analytics_reason_codes=tuple(metric.reason_codes))
            return
        emit(prefix, kind, "ANALYTICS", po, {field: getattr(metric, field) for field in fields}, derived=parents)
        ready(kind)

    po_fields = ("order_date", "material_lt_days", "overdue_open_qty", "po_status", "close_status",
                 "inventory_organization_type", "po_reference_project_id")
    emit("po", K.PO, "R1", po, {name: getattr(po, name) for name in po_fields})
    if require_ids(K.PO, po, ("po_header_id", "po_line_id", "po_line_schedule_id", "material_id", "organization_id", "supplier_id")):
        ready(K.PO)
    numeric(K.PO_AGING, "aging", metrics.aging,
            ("po_age_days", "threshold_days", "threshold_delta_days", "days_to_threshold", "days_beyond_threshold"),
            ("po.order_date", "po.material_lt_days"), (K.PO,))

    if weekly is not None:
        if require_ids(K.WEEKLY_FORECAST, weekly, ("material_id", "organization_id", "weekly_forecast_snapshot_id", "source_forecast_version_id")):
            if weekly.forecast_snapshot_date is None or any(week.week_start_date is None for week in weekly.weeks):
                missing[K.WEEKLY_FORECAST] = MissingEvidence(kind=K.WEEKLY_FORECAST, code=M.MISSING_REQUIRED_FIELD,
                                                           fields=("forecast_snapshot_date", "week_start_date"))
            elif metrics.consumption.forecast.total_forecast_qty is None:
                missing[K.WEEKLY_FORECAST] = MissingEvidence(kind=K.WEEKLY_FORECAST, code=M.NOT_COMPUTABLE,
                                                           analytics_reason_codes=tuple(metrics.consumption.forecast.reason_codes))
            else:
                emit("weekly", K.WEEKLY_FORECAST, "R4", weekly, {"good_subinventory_qty": weekly.good_subinventory_qty},
                     observed_on=weekly.forecast_snapshot_date)
                for week in sorted(weekly.weeks, key=lambda item: item.week_index):
                    emit(f"weekly.week_{week.week_index:02}", K.WEEKLY_FORECAST, "R4", weekly,
                         {"forecast_qty": week.forecast_qty}, observed_on=weekly.forecast_snapshot_date, period=week.week_start_date)
                ready(K.WEEKLY_FORECAST)
        if K.WEEKLY_FORECAST not in missing and weekly.project_contributions is not None:
            contributions = sorted(weekly.project_contributions, key=lambda item: (str(item.project_id), item.week_index))
            keys = [(item.project_id, item.week_index) for item in contributions]
            dates = {item.week_index: item.week_start_date for item in weekly.weeks}
            if len(keys) != len(set(keys)) or any(item.week_start_date != dates[item.week_index] or item.forecast_qty < 0 for item in contributions):
                raise EvidenceAssemblyError("INVALID_PROJECT_WEEK_EVIDENCE")
            emit("projects", K.PROJECT_CONTRIBUTION, "R4", weekly, {"row_count": len(contributions)}, observed_on=weekly.forecast_snapshot_date)
            for item in contributions:
                emit(f"projects.{item.project_id}.{item.week_index:02}", K.PROJECT_CONTRIBUTION, "R4", weekly,
                     {"forecast_qty": item.forecast_qty}, observed_on=weekly.forecast_snapshot_date, period=item.week_start_date,
                     keys=entity_keys(weekly) + (EntityKey(name="project_id", value=item.project_id),))
            ready(K.PROJECT_CONTRIBUTION)
    weekly_ids = tuple(fact.evidence_id for fact in facts if fact.kind == K.WEEKLY_FORECAST)
    numeric(K.PO_CONSUMPTION, "consumption", metrics.consumption, ("estimated_consumption_weeks",),
            ("po.overdue_open_qty", *weekly_ids), (K.PO, K.WEEKLY_FORECAST))
    numeric(K.INVENTORY_COVERAGE, "coverage", metrics.coverage, ("inventory_coverage_weeks",), weekly_ids, (K.WEEKLY_FORECAST,))

    if supply is not None and require_ids(K.SUPPLY_DEMAND, supply, ("material_id", "organization_id", "supply_demand_snapshot_id")):
        if supply.supply_snapshot_date is None:
            missing[K.SUPPLY_DEMAND] = MissingEvidence(kind=K.SUPPLY_DEMAND, code=M.MISSING_REQUIRED_FIELD, fields=("supply_snapshot_date",))
        elif metrics.supply_demand.supply_demand_surplus_qty is None:
            missing[K.SUPPLY_DEMAND] = MissingEvidence(kind=K.SUPPLY_DEMAND, code=M.NOT_COMPUTABLE,
                                                     analytics_reason_codes=tuple(metrics.supply_demand.reason_codes))
        else:
            emit("supply", K.SUPPLY_DEMAND, "R2", supply,
                 {"all_supply_qty": supply.all_supply_qty, "actual_demand_total_qty": supply.actual_demand_total_qty},
                 observed_on=supply.supply_snapshot_date)
            emit("supply_metric", K.SUPPLY_DEMAND, "ANALYTICS", supply,
                 {"supply_demand_surplus_qty": metrics.supply_demand.supply_demand_surplus_qty},
                 observed_on=supply.supply_snapshot_date, derived=("supply.all_supply_qty", "supply.actual_demand_total_qty"))
            ready(K.SUPPLY_DEMAND)
        if supply.mpm.employee_id is not None and supply.inventory_snapshot_date is not None:
            emit("mpm", K.MPM, "R2", supply, {"employee_id": supply.mpm.employee_id},
                 observed_on=supply.inventory_snapshot_date,
                 keys=entity_keys(supply) + (EntityKey(name="employee_id", value=supply.mpm.employee_id),))
            ready(K.MPM)

    pair_complete = previous is not None and current is not None
    for label, row in (("previous", previous), ("current", current)):
        if row is None:
            continue
        if not require_ids(K.FORECAST_PAIR, row, ("material_id", "project_id", "forecast_version_id")):
            pair_complete = False
        if row.forecast_version_sequence is None:
            pair_complete = False
            missing[K.FORECAST_PAIR] = MissingEvidence(kind=K.FORECAST_PAIR, code=M.MISSING_REQUIRED_FIELD, fields=("forecast_version_sequence",))
        if row.horizon_start_month is not None and row.horizon_end_month_exclusive is not None:
            if not row.horizon_start_month <= row.forecast_month < row.horizon_end_month_exclusive:
                raise EvidenceAssemblyError("FORECAST_PERIOD_OUTSIDE_HORIZON")
        emit(label, K.FORECAST_PAIR, "R3", row, {"forecast_qty": row.forecast_qty},
             observed_on=row.forecast_version_date, version_date=row.forecast_version_date,
             sequence=row.forecast_version_sequence, period=row.forecast_month)
    if pair_complete:
        ready(K.FORECAST_PAIR)
    numeric(K.FORECAST_CHANGE, "forecast_change", metrics.forecast_change, ("forecast_change_qty",),
            ("previous.forecast_qty", "current.forecast_qty"), (K.PO, K.FORECAST_PAIR))
    if K.FORECAST_CHANGE not in missing:
        emit("forecast_change", K.FORECAST_CHANGE, "ANALYTICS", po,
             {"forecast_change_rate": metrics.forecast_change.forecast_change_rate},
             derived=("previous.forecast_qty", "current.forecast_qty"))

    if inputs.products:
        valid = True
        for item in sorted(inputs.products, key=lambda row: (str(row.project_id), str(row.product_config_id))):
            valid &= require_ids(K.CURRENT_LIFECYCLE, item, ("material_id", "project_id", "product_config_id"))
            emit(f"config.{item.product_config_id}", K.CURRENT_LIFECYCLE, "R5", item,
                 {name: getattr(item, name) for name in ("lifecycle_stage", "product_config_version", "business_unit_name", "planning_department_name")})
        if valid:
            ready(K.CURRENT_LIFECYCLE)

    if inputs.stockpile is not None:
        query, page = inputs.stockpile, inputs.stockpile.page
        selection = page.stockpile_selection
        if selection is None:
            missing[K.STOCKPILE_HISTORY] = MissingEvidence(kind=K.STOCKPILE_HISTORY, code=M.MISSING_REQUIRED_FIELD, fields=("stockpile_selection",))
        elif page.page != 1 or page.total != len(page.items):
            missing[K.STOCKPILE_HISTORY] = MissingEvidence(kind=K.STOCKPILE_HISTORY, code=M.INCOMPLETE_COLLECTION)
        elif K.PO in missing:
            missing[K.STOCKPILE_HISTORY] = MissingEvidence(kind=K.STOCKPILE_HISTORY, code=M.MISSING_STABLE_ID)
        else:
            keys = (EntityKey(name="material_id", value=query.material_id),)
            if selection.stockpile_version_id is not None:
                keys += (EntityKey(name="stockpile_version_id", value=selection.stockpile_version_id),)
            emit("stockpile_query", K.STOCKPILE_HISTORY, "R6", po, {"record_count": page.total}, keys=keys,
                 observed_on=query.as_of_date, version_date=selection.stockpile_version_date, sequence=selection.sequence_no)
            valid = True
            for row in page.items:
                valid &= require_ids(K.STOCKPILE_HISTORY, row, ("material_id", "organization_id", "stockpile_record_id", "stockpile_version_id"))
                if not row.stockpile_tag.strip():
                    valid = False
                    missing[K.STOCKPILE_HISTORY] = MissingEvidence(kind=K.STOCKPILE_HISTORY, code=M.MISSING_REQUIRED_FIELD, fields=("stockpile_tag",))
                emit(f"stockpile.{row.stockpile_record_id}", K.STOCKPILE_HISTORY, "R6", row,
                     {name: getattr(row, name) for name in ("stockpile_tag", "target_stockpile_qty", "actual_stockpile_qty")},
                     observed_on=row.stockpile_version_date, version_date=row.stockpile_version_date, sequence=row.stockpile_version_sequence)
            if valid:
                ready(K.STOCKPILE_HISTORY)
    ids = [fact.evidence_id for fact in facts]
    if len(ids) != len(set(ids)):
        raise EvidenceAssemblyError("DUPLICATE_EVIDENCE_ADDRESS")
    return EvidenceBundle(inputs=inputs, analytics=metrics, facts=tuple(facts),
                          missing_evidence=tuple(missing[kind] for kind in K if kind in missing))
