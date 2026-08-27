from uuid import uuid4

import pytest
from sqlalchemy import Connection, Engine, delete, func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.generators.config import GenerationConfig
from app.generators.procurement.config import ProcurementGenerationConfig
from app.generators.procurement.validation import ProcurementWorldValidationError
from app.models.platform import DatasetVersion, PoHeader, PoLine, PoLineSchedule
from app.services.dataset_generation import DatasetGenerationService
from app.services.procurement_generation import (
    ProcurementGenerationError,
    ProcurementGenerationService,
)


pytestmark = pytest.mark.integration


def _generate_master(session: Session, seed: int, suffix: str):
    return DatasetGenerationService(session).generate(
        GenerationConfig.small_test(random_seed=seed), f"procurement-test-{suffix}"
    )


def test_service_writes_reuses_and_keeps_dataset_generating(migrated_database: Engine) -> None:
    suffix = uuid4().hex[:8]
    with Session(migrated_database, expire_on_commit=False) as session:
        master = _generate_master(session, 31001, suffix)
        config = ProcurementGenerationConfig.small_test(random_seed=41001)
        first = ProcurementGenerationService(session).generate(master.dataset_version_id, config)
        reused = ProcurementGenerationService(session).generate(master.dataset_version_id, config)
        assert reused.reused is True
        assert reused.procurement_content_hash == first.procurement_content_hash
        dataset = session.get(DatasetVersion, master.dataset_version_id)
        assert dataset.status == "GENERATING"
        assert dataset.business_content_hash is None
        session.rollback()
        with pytest.raises(ProcurementGenerationError, match="PROCUREMENT_CONFIG_CONFLICT"):
            ProcurementGenerationService(session).generate(
                master.dataset_version_id,
                ProcurementGenerationConfig.small_test(random_seed=41002),
            )
        session.delete(dataset)
        session.commit()


class _RejectingValidator:
    def validate(self, *args, **kwargs) -> None:
        raise ProcurementWorldValidationError("injected procurement failure")


def test_service_failure_rolls_back_all_procurement_facts(migrated_database: Engine) -> None:
    suffix = uuid4().hex[:8]
    with Session(migrated_database, expire_on_commit=False) as session:
        master = _generate_master(session, 31002, suffix)
        dataset_id = master.dataset_version_id
        with pytest.raises(ProcurementWorldValidationError, match="injected"):
            ProcurementGenerationService(session, validator=_RejectingValidator()).generate(
                dataset_id, ProcurementGenerationConfig.small_test(random_seed=41003)
            )
        assert session.scalar(
            select(PoHeader).where(PoHeader.dataset_version_id == dataset_id)
        ) is None
        dataset = session.get(DatasetVersion, dataset_id)
        session.delete(dataset)
        session.commit()


def test_service_rejects_incomplete_procurement_world(migrated_database: Engine) -> None:
    suffix = uuid4().hex[:8]
    with Session(migrated_database, expire_on_commit=False) as session:
        master = _generate_master(session, 31003, suffix)
        config = ProcurementGenerationConfig.small_test(random_seed=41004)
        ProcurementGenerationService(session).generate(master.dataset_version_id, config)
        session.execute(
            delete(PoLineSchedule).where(
                PoLineSchedule.dataset_version_id == master.dataset_version_id
            )
        )
        session.commit()
        with pytest.raises(ProcurementGenerationError, match="INCOMPLETE_PROCUREMENT_WORLD"):
            ProcurementGenerationService(session).generate(master.dataset_version_id, config)
        dataset = session.get(DatasetVersion, master.dataset_version_id)
        session.delete(dataset)
        session.commit()


def _generate_inside_connection(connection: Connection, seed: int):
    suffix = uuid4().hex[:8]
    with Session(connection, expire_on_commit=False) as session:
        master = _generate_master(session, seed, suffix)
        procurement = ProcurementGenerationService(session).generate(
            master.dataset_version_id,
            ProcurementGenerationConfig.small_test(random_seed=seed + 1000),
        )
    return master, procurement


def test_multi_shipment_and_database_quantity_constraints(
    database_connection: Connection,
) -> None:
    _, result = _generate_inside_connection(database_connection, 32001)
    schedule = result.world.po_line_schedules[0]
    second_schedule = {
        "dataset_version_id": result.dataset_version_id,
        "po_line_schedule_id": uuid4(),
        "po_line_id": schedule.po_line_id,
        "shipment_number": 2,
        "schedule_qty": 1,
        "schedule_received_qty": 0,
        "due_date": schedule.due_date,
        "close_status": "OPEN",
    }
    database_connection.execute(insert(PoLineSchedule), second_schedule)
    assert database_connection.scalar(
        select(PoLineSchedule)
        .where(PoLineSchedule.po_line_id == schedule.po_line_id)
        .with_only_columns(func.count())
    ) == 2

    for values in (
        {**second_schedule, "po_line_schedule_id": uuid4(), "shipment_number": 3, "schedule_qty": -1},
        {
            **second_schedule,
            "po_line_schedule_id": uuid4(),
            "shipment_number": 4,
            "schedule_qty": 1,
            "schedule_received_qty": 2,
        },
    ):
        with pytest.raises(IntegrityError):
            with database_connection.begin_nested():
                database_connection.execute(insert(PoLineSchedule), values)


def test_duplicate_numbers_and_cross_dataset_fk_are_rejected(
    database_connection: Connection,
) -> None:
    first_master, first = _generate_inside_connection(database_connection, 33001)
    second_master, _ = _generate_inside_connection(database_connection, 33002)
    line = first.world.po_lines[0]
    schedule = first.world.po_line_schedules[0]
    with pytest.raises(IntegrityError):
        with database_connection.begin_nested():
            database_connection.execute(
                insert(PoLine),
                {
                    column.name: getattr(line, column.name)
                    for column in PoLine.__table__.columns
                    if column.name != "created_at"
                }
                | {"po_line_id": uuid4()},
            )
    with pytest.raises(IntegrityError):
        with database_connection.begin_nested():
            database_connection.execute(
                insert(PoLineSchedule),
                {
                    column.name: getattr(schedule, column.name)
                    for column in PoLineSchedule.__table__.columns
                    if column.name != "created_at"
                }
                | {"po_line_schedule_id": uuid4()},
            )

    header = first.world.po_headers[0]
    foreign_supplier = second_master.world.suppliers[0].supplier_id
    with pytest.raises(IntegrityError):
        with database_connection.begin_nested():
            database_connection.execute(
                insert(PoHeader),
                {
                    column.name: getattr(header, column.name)
                    for column in PoHeader.__table__.columns
                    if column.name != "created_at"
                }
                | {
                    "po_header_id": uuid4(),
                    "po_number": "PO-CROSS-DATASET",
                    "supplier_id": foreign_supplier,
                },
            )
