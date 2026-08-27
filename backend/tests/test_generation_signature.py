from app.generators.config import GenerationConfig
from app.generators.signature import canonical_json, generation_signature


def test_signature_is_stable_and_order_independent_for_options() -> None:
    left = GenerationConfig.small_test(
        generation_options={"historical_mpm_switches": True, "alternate_supplier_ratio_percent": 35}
    )
    right = GenerationConfig.small_test(
        generation_options={"alternate_supplier_ratio_percent": 35, "historical_mpm_switches": True}
    )
    assert generation_signature(left) == generation_signature(right)
    assert canonical_json(left) == canonical_json(right)


def test_signature_changes_with_seed_and_snapshot_date() -> None:
    baseline = GenerationConfig.small_test()
    assert generation_signature(baseline) != generation_signature(
        GenerationConfig.small_test(random_seed=124)
    )
    assert generation_signature(baseline) != generation_signature(
        GenerationConfig.small_test(snapshot_date="2026-08-27")
    )
