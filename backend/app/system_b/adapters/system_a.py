"""HTTP-only System A consumer. All report methods return one explicit page."""

import json
from collections.abc import Callable, Iterator
from decimal import Decimal
from typing import TypeVar
from uuid import UUID

import httpx
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.system_b import models
from app.system_b.adapters import dto, mapping
from app.system_b.adapters.errors import (
    SystemAHTTPError,
    SystemANotFoundError,
    SystemAResponseValidationError,
    SystemAUnavailableError,
)


S = TypeVar("S", bound=dto.SourceDTO)
T = TypeVar("T", bound=models.CanonicalModel)


class SystemAAdapter:
    def __init__(self, settings: Settings | None = None, *, transport: httpx.BaseTransport | None = None):
        configured = settings if settings is not None else get_settings()
        if configured.system_a_base_url is None:
            raise ValueError("SYSTEM_A_BASE_URL is required to create SystemAAdapter")
        self._client = httpx.Client(
            base_url=str(configured.system_a_base_url).rstrip("/") + "/",
            timeout=httpx.Timeout(configured.system_a_timeout_seconds),
            transport=transport,
            follow_redirects=False,
            trust_env=False,
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self) -> None:
        self._client.close()

    def _get(self, path: str, response_type: type[S], params: dict | None = None) -> S:
        try:
            response = self._client.get(path, params=params)
        except httpx.RequestError:
            raise SystemAUnavailableError("System A request failed or timed out") from None
        status = response.status_code
        if status == 404:
            raise SystemANotFoundError("System A resource was not found", status_code=status)
        if 500 <= status <= 599:
            raise SystemAUnavailableError("System A returned a server error", status_code=status)
        if status != 200:
            raise SystemAHTTPError("System A returned an unexpected HTTP status", status_code=status)
        try:
            # Never convert JSON decimals through binary floating point first.
            payload = json.loads(response.content, parse_float=Decimal)
            return response_type.model_validate(payload)
        except (ValueError, UnicodeDecodeError):
            raise SystemAResponseValidationError("System A response failed validation") from None

    @staticmethod
    def _dataset_id(value: UUID) -> UUID:
        if not isinstance(value, UUID):
            raise TypeError("dataset_version_id must be an explicit UUID")
        return value

    def list_datasets(self) -> tuple[models.DatasetMetadata, ...]:
        result = self._get("datasets", dto.DatasetListDTO)
        if result.total != len(result.items):
            raise SystemAResponseValidationError("System A dataset list total is inconsistent")
        return tuple(models.DatasetMetadata(**item.model_dump()) for item in result.items)

    def get_dataset(self, dataset_version_id: UUID) -> models.DatasetMetadata:
        did = self._dataset_id(dataset_version_id)
        result = self._get(f"datasets/{did}", dto.DatasetDTO)
        if result.dataset_version_id != did:
            raise SystemAResponseValidationError("System A returned a different dataset")
        return models.DatasetMetadata(**result.model_dump())

    def _page(
        self, path: str, source_type: type[S], canonical_type: type[T],
        mapper: Callable[[S, dict], T], dataset_version_id: UUID,
        page: int, page_size: int, filters: dict,
    ) -> models.CanonicalPage[T]:
        did = self._dataset_id(dataset_version_id)
        if type(page) is not int or page < 1 or type(page_size) is not int or not 1 <= page_size <= 500:
            raise ValueError("page must be positive and page_size must be between 1 and 500")
        params = {"dataset_version_id": str(did), "page": page, "page_size": page_size}
        params.update({key: value for key, value in filters.items() if value is not None})
        result = self._get(f"reports/{path}", dto.ReportPageDTO[source_type], params)
        if result.dataset_version_id != did or result.page != page or result.page_size != page_size:
            raise SystemAResponseValidationError("System A returned inconsistent request metadata")
        expected_count = min(page_size, max(result.total - (page - 1) * page_size, 0))
        if len(result.items) != expected_count:
            raise SystemAResponseValidationError("System A returned inconsistent pagination")
        context = {"dataset_version_id": did, "snapshot_date": result.snapshot_date}
        for row in result.items:
            if hasattr(row, "snapshot_date") and row.snapshot_date != result.snapshot_date:
                raise SystemAResponseValidationError("System A row snapshot differs from its page")
        try:
            return models.CanonicalPage[canonical_type](
                **context, page=page, page_size=page_size, total=result.total,
                items=tuple(mapper(row, context) for row in result.items),
            )
        except ValidationError:
            raise SystemAResponseValidationError("System A response could not be mapped") from None

    def purchase_orders(
        self, dataset_version_id: UUID, *, page: int = 1, page_size: int = 100,
        material_code: str | None = None, supplier: str | None = None, buyer: str | None = None,
        project: str | None = None, po_number: str | None = None,
    ) -> models.CanonicalPage[models.PurchaseOrder]:
        return self._page("overdue-pos", dto.PurchaseOrderDTO, models.PurchaseOrder, mapping.purchase_order,
                          dataset_version_id, page, page_size,
                          {"material_code": material_code, "supplier": supplier, "buyer": buyer,
                           "project": project, "po_number": po_number})

    def material_supply_demand(
        self, dataset_version_id: UUID, *, page: int = 1, page_size: int = 100,
        material_code: str | None = None, mpm: str | None = None, surplus_sign: str | None = None,
    ) -> models.CanonicalPage[models.MaterialSupplyDemand]:
        return self._page("material-supply-demand", dto.SupplyDemandDTO, models.MaterialSupplyDemand,
                          mapping.supply_demand, dataset_version_id, page, page_size,
                          {"material_code": material_code, "mpm": mpm, "surplus_sign": surplus_sign})

    def forecast_history(
        self, dataset_version_id: UUID, *, page: int = 1, page_size: int = 100,
        material_code: str | None = None, project: str | None = None, po_number: str | None = None,
        forecast_version: str | None = None, window_role: str | None = None,
    ) -> models.CanonicalPage[models.ForecastSnapshot]:
        return self._page("forecast-history", dto.ForecastDTO, models.ForecastSnapshot, mapping.forecast,
                          dataset_version_id, page, page_size,
                          {"material_code": material_code, "project": project, "po_number": po_number,
                           "forecast_version": forecast_version, "window_role": window_role})

    def latest_13w_forecast(
        self, dataset_version_id: UUID, *, page: int = 1, page_size: int = 100,
        material_code: str | None = None,
    ) -> models.CanonicalPage[models.WeeklyForecastSnapshot]:
        return self._page("latest-13w-forecast", dto.WeeklyForecastDTO, models.WeeklyForecastSnapshot,
                          mapping.weekly_forecast, dataset_version_id, page, page_size,
                          {"material_code": material_code})

    def product_configurations(
        self, dataset_version_id: UUID, *, page: int = 1, page_size: int = 100,
        project: str | None = None, material_code: str | None = None,
        business_unit: str | None = None, planning_department: str | None = None, lifecycle: str | None = None,
    ) -> models.CanonicalPage[models.ProductConfig]:
        return self._page("product-configurations", dto.ProductConfigDTO, models.ProductConfig,
                          mapping.product_config, dataset_version_id, page, page_size,
                          {"project": project, "material_code": material_code, "business_unit": business_unit,
                           "planning_department": planning_department, "lifecycle": lifecycle})

    def stockpile(
        self, dataset_version_id: UUID, *, page: int = 1, page_size: int = 100,
        material_code: str | None = None,
    ) -> models.CanonicalPage[models.StockpileRecord]:
        return self._page("stockpile", dto.StockpileDTO, models.StockpileRecord, mapping.stockpile,
                          dataset_version_id, page, page_size, {"material_code": material_code})

    def iter_pages(
        self, fetch_page: Callable[..., models.CanonicalPage[T]], dataset_version_id: UUID,
        *, page_size: int = 100, **filters,
    ) -> Iterator[models.CanonicalPage[T]]:
        """Stream complete pages; a later failure invalidates collection completeness."""
        page = 1
        identity = None
        while True:
            batch = fetch_page(dataset_version_id, page=page, page_size=page_size, **filters)
            current = (batch.dataset_version_id, batch.snapshot_date, batch.total)
            if identity is not None and current != identity:
                raise SystemAResponseValidationError("System A metadata changed between pages")
            identity = current
            yield batch
            if page * page_size >= batch.total:
                return
            page += 1
