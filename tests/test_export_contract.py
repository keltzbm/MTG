import pytest


@pytest.mark.skip(reason="scaffold")
def test_export_never_writes_outside_generated_and_log():
    """The contract that protects authored prose."""


@pytest.mark.skip(reason="scaffold")
def test_stub_deck_note_does_not_overwrite_existing():
    """Stub creation is create-if-absent, never overwrite."""
