"""Pure deterministic traffic share calculation and validation for stream offers."""

from collections.abc import Sequence
from typing import cast

from adrobot.core.exceptions import DomainValidationError
from adrobot.db.models import StreamOffer


def _active_sort_key(offer: StreamOffer) -> tuple[bool, int]:
    """Order persisted offers by ascending DB id, placing newly staged offers (id=None) last."""
    offer_id = cast("int | None", offer.id)
    return (offer_id is None, offer_id or 0)


def recalculate_shares(offers: Sequence[StreamOffer]) -> None:
    """Recalculate integer traffic shares across active offers so they sum strictly to 100.

    Removed offers are forced to ``share = 0`` and ``is_pinned = False``. Pinned active offers
    keep their current shares; any remaining percentage ``100 - sum(pinned)`` is split evenly
    across unpinned active offers with the integer remainder added to the last unpinned offer.
    """
    for offer in offers:
        if offer.status != "active":
            offer.share = 0
            offer.is_pinned = False

    active = sorted((o for o in offers if o.status == "active"), key=_active_sort_key)
    if not active:
        return

    pinned = [o for o in active if o.is_pinned]
    unpinned = [o for o in active if not o.is_pinned]

    pinned_sum = sum(o.share for o in pinned)
    if pinned_sum > 100:
        raise DomainValidationError(
            "Pinned shares cannot exceed 100%",
            details={"pinned_sum": str(pinned_sum)},
        )

    if not unpinned:
        if pinned_sum != 100:
            raise DomainValidationError(
                "All offers are pinned, so their shares must sum to 100%",
                details={"pinned_sum": str(pinned_sum)},
            )
        return

    remaining = 100 - pinned_sum
    base_share = remaining // len(unpinned)
    remainder = remaining % len(unpinned)

    for offer in unpinned:
        offer.share = base_share
    unpinned[-1].share += remainder


def validate_stream_for_push(offers: Sequence[StreamOffer]) -> tuple[bool, str | None]:
    """Validate whether a stream's active offers satisfy all Keitaro push invariants."""
    active = [o for o in offers if o.status == "active"]
    if len(active) < 1:
        return False, "Stream must have at least one active offer"

    if sum(o.share for o in active) != 100:
        return False, "Active offer shares must sum to 100%"

    if any(o.share < 1 for o in active):
        return False, "Each active offer must have a share of at least 1%"

    return True, None
