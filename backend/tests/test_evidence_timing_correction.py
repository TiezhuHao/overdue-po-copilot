import pytest
from sqlalchemy import delete, event, select, update
from sqlalchemy.orm import Session

from app.generators.evidence_foundation.config import EvidenceFoundationConfig
from app.generators.evidence_foundation.world import EvidenceFoundationWorld, evidence_identity_signature
from app.generators.signature import content_hash
from app.models.platform import DatasetVersion
from app.models.platform.evidence_foundation import EVIDENCE_MODELS, DemandSignal, DemandSignalPoint
from app.services.evidence_foundation_generation import EvidenceFoundationError, EvidenceFoundationGenerationService
from app.services.evidence_timing_correction import EvidenceTimingCorrectionService
from tests.test_evidence_foundation_integration import PC, SC, foundation, generate

pytestmark = pytest.mark.integration


def loaded(session, dataset_id):
    return EvidenceFoundationWorld(**{m.__tablename__: list(session.scalars(select(m).where(m.dataset_version_id == dataset_id))) for m in EVIDENCE_MODELS})


@pytest.fixture(scope='module')
def prior_evidence(migrated_database):
    with Session(migrated_database) as session:
        dataset_id = foundation(session, 75005)
        session.execute(update(DatasetVersion).where(DatasetVersion.dataset_version_id == dataset_id).values(version_name='demo-master-v1'))
        session.commit()
        current = generate(session, dataset_id)
        dataset = session.get(DatasetVersion, dataset_id)
        service = EvidenceFoundationGenerationService(session)
        _, procurement, _, master_hash, scenario_hash = service._prerequisites(dataset, PC, SC)
        identity = evidence_identity_signature(dataset.generation_signature, master_hash, procurement.procurement_facts_hash(), scenario_hash, SC, EvidenceFoundationConfig())
        # An explicitly hashed prior source fixture; no legacy implementation is
        # retained or imported into production to support the correction.
        point = current.world.demand_signal_points[0]
        session.execute(update(DemandSignalPoint).where(DemandSignalPoint.dataset_version_id == dataset_id, DemandSignalPoint.demand_signal_point_id == point.demand_signal_point_id).values(demand_qty=point.demand_qty + 1))
        for signal in current.world.demand_signals:
            session.execute(update(DemandSignal).where(DemandSignal.dataset_version_id == dataset_id, DemandSignal.demand_signal_id == signal.demand_signal_id).values(scenario_generation_key=content_hash([identity, f'{signal.material_id}:{signal.project_id}'])))
        session.commit()
        old_hash = loaded(session, dataset_id).content_hash(identity)
    try:
        yield dataset_id, old_hash, identity, current
    finally:
        with Session(migrated_database) as session:
            session.execute(delete(DatasetVersion).where(DatasetVersion.dataset_version_id == dataset_id))
            session.commit()


def correct(session, prior, **kwargs):
    return EvidenceTimingCorrectionService(session).correct(prior[0], prior[1], procurement_config=PC, scenario_config=SC, **kwargs)


def test_correction_roundtrip_idempotency_and_structural_preservation(database_connection, prior_evidence):
    with Session(database_connection, join_transaction_mode='create_savepoint') as session:
        result = correct(session, prior_evidence)
        assert result.evidence_foundation_content_hash == prior_evidence[3].evidence_foundation_content_hash
        assert not result.reused
        same = correct(session, prior_evidence)
        assert same.reused and same.evidence_foundation_content_hash == result.evidence_foundation_content_hash
        dataset = session.get(DatasetVersion, prior_evidence[0])
        assert dataset.status == 'GENERATING' and dataset.business_content_hash is None


@pytest.mark.parametrize('gate', ['READY', 'wrong_name', 'wrong_hash'])
def test_correction_safety_gates(database_connection, prior_evidence, gate):
    prior = prior_evidence
    if gate == 'READY':
        database_connection.execute(update(DatasetVersion).where(DatasetVersion.dataset_version_id == prior[0]).values(status='READY'))
        error = 'DATASET_NOT_GENERATING'
    elif gate == 'wrong_name':
        database_connection.execute(update(DatasetVersion).where(DatasetVersion.dataset_version_id == prior[0]).values(version_name='unrelated-dataset'))
        error = 'CORRECTION_TARGET_NOT_DEMO'
    else:
        prior = (prior[0], '0' * 64, *prior[2:])
        error = 'CORRECTION_OLD_HASH_MISMATCH'
    with Session(database_connection, join_transaction_mode='create_savepoint') as session:
        with pytest.raises(EvidenceFoundationError, match=error):
            correct(session, prior)


def test_correction_failure_rolls_back_prior_source(database_connection, prior_evidence):
    def reject(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith('INSERT INTO platform.demand_signal_revisions'):
            raise RuntimeError('injected correction failure')
    event.listen(database_connection, 'before_cursor_execute', reject)
    try:
        with Session(database_connection, join_transaction_mode='create_savepoint') as session:
            with pytest.raises(RuntimeError, match='injected correction failure'):
                correct(session, prior_evidence)
    finally:
        event.remove(database_connection, 'before_cursor_execute', reject)
    with Session(database_connection, join_transaction_mode='create_savepoint') as session:
        assert loaded(session, prior_evidence[0]).content_hash(prior_evidence[2]) == prior_evidence[1]


def test_correction_leaves_another_dataset_unchanged(migrated_database, prior_evidence):
    with Session(migrated_database) as session:
        other_id = foundation(session, 75006)
        other = generate(session, other_id)
    try:
        with migrated_database.connect() as connection:
            outer = connection.begin()
            try:
                with Session(connection, join_transaction_mode='create_savepoint') as session:
                    correct(session, prior_evidence)
                    assert loaded(session, other_id).content_hash(other.evidence_foundation_signature) == other.evidence_foundation_content_hash
            finally:
                outer.rollback()
    finally:
        with Session(migrated_database) as session:
            session.execute(delete(DatasetVersion).where(DatasetVersion.dataset_version_id == other_id))
            session.commit()
