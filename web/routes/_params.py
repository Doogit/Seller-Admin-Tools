"""Shared query/form parameter parsing + snapshot-selection resolution for the
tool routes. Defensive: empty/garbage values coerce to None (fall back to a
default) rather than 404-ing on int/float coercion of an empty string."""

from __future__ import annotations


def cid(current_id: str | None) -> int | None:
    try:
        return int(current_id) if current_id not in (None, "") else None
    except (TypeError, ValueError):
        return None


def pid(prior_id: str | None) -> int | None:
    """Compare/prior select: "" (explicit none) -> None, else int."""
    try:
        return int(prior_id) if prior_id not in (None, "") else None
    except (TypeError, ValueError):
        return None


def quota(value: str | None) -> float | None:
    try:
        q = float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
    return q or None


def resolve(current_id, prior_id, options):
    """Pick a valid (current, prior). Falls back to the default selection when
    current is unknown; drops a prior that equals current or isn't a snapshot.
    Respects an explicit prior=None (user chose '— none —')."""
    ids = [o[0] for o in options]
    if not options:
        return None, None
    if current_id not in ids:
        current = options[0][0]
        return current, (options[1][0] if len(options) > 1 else None)
    if prior_id is not None and (prior_id not in ids or prior_id == current_id):
        rest = [i for i in ids if i != current_id]
        prior_id = rest[0] if rest else None
    return current_id, prior_id
