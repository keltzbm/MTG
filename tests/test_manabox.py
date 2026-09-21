import pytest


@pytest.mark.skip(reason="scaffold")
def test_bom_encoded_export_parses():
    """ManaBox writes a UTF-8 BOM; utf-8 (no -sig) mangles the first header."""


@pytest.mark.skip(reason="scaffold")
def test_quantity_sums_across_printings():
    """Same card on several rows, one per printing."""
