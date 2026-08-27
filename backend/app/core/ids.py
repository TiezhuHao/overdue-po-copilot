from uuid import UUID, uuid5


SYSTEM_A_NAMESPACE = UUID("f5a774c7-1cbd-57d4-847e-c8f63fd7dfaf")


def deterministic_uuid(*parts: object, namespace: UUID = SYSTEM_A_NAMESPACE) -> UUID:
    """Build a stable UUID from an ordered, explicit business identity."""
    if not parts:
        raise ValueError("at least one identity part is required")
    canonical_parts = [str(part).strip() for part in parts]
    if any(not part for part in canonical_parts):
        raise ValueError("identity parts must not be empty")
    return uuid5(namespace, "\x1f".join(canonical_parts))
