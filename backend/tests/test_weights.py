"""Unit tests for deterministic share recalculation and stream push validation."""

import pytest

from adrobot.core.exceptions import DomainValidationError
from adrobot.db.models import OfferStatus, StreamOffer
from adrobot.services.weights import recalculate_shares, validate_stream_for_push


def _make_offer(
    *,
    offer_id: int | None,
    keitaro_offer_id: int,
    share: int = 0,
    is_pinned: bool = False,
    status: OfferStatus = "active",
) -> StreamOffer:
    offer = StreamOffer(
        stream_id=1,
        keitaro_offer_id=keitaro_offer_id,
        offer_name=f"Offer {keitaro_offer_id}",
        share=share,
        is_pinned=is_pinned,
        status=status,
    )
    if offer_id is not None:
        offer.id = offer_id
    return offer


def test_recalculate_shares_equal_splits_and_remainder_on_last() -> None:
    """Verify 1, 2, 3, and 4 unpinned offers split 100 with remainder on last unpinned."""
    single = [_make_offer(offer_id=1, keitaro_offer_id=10)]
    recalculate_shares(single)
    assert [o.share for o in single] == [100]

    pair = [
        _make_offer(offer_id=1, keitaro_offer_id=10),
        _make_offer(offer_id=2, keitaro_offer_id=20),
    ]
    recalculate_shares(pair)
    assert [o.share for o in pair] == [50, 50]

    triple = [
        _make_offer(offer_id=1, keitaro_offer_id=10),
        _make_offer(offer_id=2, keitaro_offer_id=20),
        _make_offer(offer_id=None, keitaro_offer_id=30),
    ]
    recalculate_shares(triple)
    assert [o.share for o in triple] == [33, 33, 34]


def test_recalculate_shares_places_unpersisted_offers_last_deterministically() -> None:
    """Verify offers with id=None are sorted after persisted offers regardless of input order."""
    new_offer = _make_offer(offer_id=None, keitaro_offer_id=99)
    existing_b = _make_offer(offer_id=20, keitaro_offer_id=2)
    existing_a = _make_offer(offer_id=10, keitaro_offer_id=1)

    recalculate_shares([new_offer, existing_b, existing_a])
    assert existing_a.share == 33
    assert existing_b.share == 33
    assert new_offer.share == 34


def test_recalculate_shares_preserves_pinned_and_distributes_remainder() -> None:
    """Verify pinned offers keep exact shares while remaining share splits over unpinned."""
    pinned = _make_offer(offer_id=1, keitaro_offer_id=10, share=50, is_pinned=True)
    unpinned_1 = _make_offer(offer_id=2, keitaro_offer_id=20)
    unpinned_2 = _make_offer(offer_id=3, keitaro_offer_id=30)
    unpinned_3 = _make_offer(offer_id=None, keitaro_offer_id=40)

    recalculate_shares([pinned, unpinned_1, unpinned_2, unpinned_3])
    assert pinned.share == 50
    assert [unpinned_1.share, unpinned_2.share, unpinned_3.share] == [16, 16, 18]
    assert sum(o.share for o in [pinned, unpinned_1, unpinned_2, unpinned_3]) == 100


def test_recalculate_shares_resets_removed_offers_and_handles_empty_active() -> None:
    """Verify removed offers always get share=0, is_pinned=False and 0 active offers is safe."""
    removed_1 = _make_offer(
        offer_id=1, keitaro_offer_id=10, share=40, is_pinned=True, status="removed"
    )
    removed_2 = _make_offer(
        offer_id=2, keitaro_offer_id=20, share=60, is_pinned=False, status="removed"
    )
    recalculate_shares([removed_1, removed_2])
    assert removed_1.share == 0
    assert removed_1.is_pinned is False
    assert removed_2.share == 0

    can_push, err = validate_stream_for_push([removed_1, removed_2])
    assert can_push is False
    assert err == "Stream must have at least one active offer"


def test_recalculate_shares_rejects_pinned_overflow_and_all_pinned_bad_sum() -> None:
    """Verify DomainValidationError on pinned_sum > 100 or all pinned summing != 100."""
    overflow = [
        _make_offer(offer_id=1, keitaro_offer_id=10, share=60, is_pinned=True),
        _make_offer(offer_id=2, keitaro_offer_id=20, share=50, is_pinned=True),
    ]
    with pytest.raises(DomainValidationError, match="cannot exceed 100%"):
        recalculate_shares(overflow)

    under_sum_all_pinned = [
        _make_offer(offer_id=1, keitaro_offer_id=10, share=40, is_pinned=True),
        _make_offer(offer_id=2, keitaro_offer_id=20, share=50, is_pinned=True),
    ]
    with pytest.raises(DomainValidationError, match="must sum to 100%"):
        recalculate_shares(under_sum_all_pinned)

    valid_all_pinned = [
        _make_offer(offer_id=1, keitaro_offer_id=10, share=40, is_pinned=True),
        _make_offer(offer_id=2, keitaro_offer_id=20, share=60, is_pinned=True),
    ]
    recalculate_shares(valid_all_pinned)
    assert validate_stream_for_push(valid_all_pinned) == (True, None)


def test_validate_stream_for_push_rejects_bad_sum_or_zero_share_active_offer() -> None:
    """Verify validate_stream_for_push enforces sum == 100 and share >= 1 for active offers."""
    bad_sum = [
        _make_offer(offer_id=1, keitaro_offer_id=10, share=50),
        _make_offer(offer_id=2, keitaro_offer_id=20, share=40),
    ]
    assert validate_stream_for_push(bad_sum) == (False, "Active offer shares must sum to 100%")

    zero_share_offer = [
        _make_offer(offer_id=1, keitaro_offer_id=10, share=100, is_pinned=True),
        _make_offer(offer_id=2, keitaro_offer_id=20, share=0, is_pinned=False),
    ]
    assert validate_stream_for_push(zero_share_offer) == (
        False,
        "Each active offer must have a share of at least 1%",
    )


def test_recalculate_shares_rejects_when_remaining_cannot_cover_unpinned() -> None:
    """Verify pinned 100% plus an unpinned offer, or remaining < unpinned count, is rejected."""
    full_pinned_plus_new = [
        _make_offer(offer_id=1, keitaro_offer_id=10, share=100, is_pinned=True),
        _make_offer(offer_id=None, keitaro_offer_id=20),
    ]
    with pytest.raises(DomainValidationError, match="too small"):
        recalculate_shares(full_pinned_plus_new)

    tight = [
        _make_offer(offer_id=1, keitaro_offer_id=10, share=98, is_pinned=True),
        _make_offer(offer_id=2, keitaro_offer_id=20),
        _make_offer(offer_id=3, keitaro_offer_id=30),
        _make_offer(offer_id=4, keitaro_offer_id=40),
    ]
    with pytest.raises(DomainValidationError, match="too small"):
        recalculate_shares(tight)

    exact = [
        _make_offer(offer_id=1, keitaro_offer_id=10, share=98, is_pinned=True),
        _make_offer(offer_id=2, keitaro_offer_id=20),
        _make_offer(offer_id=3, keitaro_offer_id=30),
    ]
    recalculate_shares(exact)
    assert [o.share for o in exact] == [98, 1, 1]
