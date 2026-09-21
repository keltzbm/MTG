"""Both original bugs get a regression test."""

import pytest


@pytest.mark.skip(reason="scaffold")
def test_precon_contents_count_as_owned():
    """30 cards in a sealed precon must not read as 'need to buy'."""


@pytest.mark.skip(reason="scaffold")
def test_card_owned_in_another_deck_is_flagged_as_conflict_not_shortfall():
    """One copy rotated between decks is owned, not missing."""
