"""Structural transformations only: no joins, arithmetic or diagnosis."""

from app.system_b import models
from app.system_b.adapters import dto


def purchase_order(row: dto.PurchaseOrderDTO, context: dict) -> models.PurchaseOrder:
    return models.PurchaseOrder(**(row.model_dump() | context))


def supply_demand(row: dto.SupplyDemandDTO, context: dict) -> models.MaterialSupplyDemand:
    values = row.model_dump()
    contact = models.MaterialMpmContact(
        employee_code=values.pop("mpm_code"),
        employee_name=values.pop("mpm_name"),
        department_name=values.pop("mpm_department_name"),
        employee_id=values.pop("mpm_employee_id"),
    )
    return models.MaterialSupplyDemand(**values, **context, mpm=contact)


def forecast(row: dto.ForecastDTO, context: dict) -> models.ForecastSnapshot:
    return models.ForecastSnapshot(**row.model_dump(), **context)


def weekly_forecast(row: dto.WeeklyForecastDTO, context: dict) -> models.WeeklyForecastSnapshot:
    values = row.model_dump()
    evidence = values.pop("weeks")
    weeks = tuple(models.WeekForecast(week_index=index, forecast_qty=values.pop(f"week_{index:02d}_forecast_qty"))
                  for index in range(1, 14))
    if evidence is not None:
        weeks = tuple(models.WeekForecast(**item) for item in sorted(evidence, key=lambda item: item["week_index"]))
    return models.WeeklyForecastSnapshot(**(values | context), weeks=weeks)


def product_config(row: dto.ProductConfigDTO, context: dict) -> models.ProductConfig:
    return models.ProductConfig(**row.model_dump(), **context)


def stockpile(row: dto.StockpileDTO, context: dict) -> models.StockpileRecord:
    values = row.model_dump()
    values["stockpile_tag"] = values.pop("stockpile_nature")
    values["target_stockpile_qty"] = values.pop("planned_stockpile_qty")
    return models.StockpileRecord(**values, **context)
