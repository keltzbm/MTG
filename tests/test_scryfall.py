from mtg.ingest.scryfall import download_url


def test_prefers_jsonl_link_after_the_2026_format_change():
    info = {"jsonl_download_uri": "https://x/default.jsonl.gz", "download_uri": "https://x/default.json"}
    assert download_url(info) == ("https://x/default.jsonl.gz", "default-cards.jsonl.gz")


def test_falls_back_to_the_old_array_link():
    assert download_url({"download_uri": "https://x/d.json"}) == ("https://x/d.json", "default-cards.json")
