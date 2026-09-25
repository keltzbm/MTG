import gzip
import json
import os
from datetime import UTC, date, datetime

import pytest

from riffle import net
from riffle.ingest import scryfall
from riffle.ingest.scryfall import download_url


def test_prefers_jsonl_link_after_the_2026_format_change():
    info = {"jsonl_download_uri": "https://x/default.jsonl.gz", "download_uri": "https://x/default.json"}
    assert download_url(info) == ("https://x/default.jsonl.gz", "default-cards.jsonl.gz")


def test_falls_back_to_the_old_array_link():
    assert download_url({"download_uri": "https://x/d.json"}) == ("https://x/d.json", "default-cards.json")


# ---- daily price snapshots ----------------------------------------------------

CARDS = [
    {"id": "aaa", "name": "Sol Ring", "prices": {"usd": "1.50", "usd_foil": None, "eur": "1.20"}},
    {"id": "bbb", "name": "Island", "prices": {"usd": "0.05", "usd_foil": "0.30", "tix": None}},
]


def write_bulk(data_dir, name="default-cards.jsonl.gz", updated_at="2026-09-24T09:05:40.725+00:00"):
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / name
    if name.endswith(".jsonl.gz"):
        with gzip.open(path, "wt", encoding="utf-8") as f:
            f.writelines(json.dumps(c) + "\n" for c in CARDS)
    else:
        path.write_text(json.dumps(CARDS))
    if updated_at:
        (data_dir / "bulk-meta.json").write_text(json.dumps({"updated_at": updated_at, "rows": 2}))
    return path


def snapshot_lines(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def test_snapshot_keeps_each_printing_prices_for_the_bulk_day(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    write_bulk(tmp_path / "riffle")
    path, written = scryfall.snapshot_prices()
    assert written and path == tmp_path / "riffle" / "scryfall" / "daily" / "2026-09-24.jsonl.gz"
    assert snapshot_lines(path) == [{"id": c["id"], "prices": c["prices"]} for c in CARDS]
    assert scryfall.snapshot_prices() == (path, False)


def test_snapshot_reads_the_old_array_format_and_dates_by_mtime_without_meta(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    bulk = write_bulk(tmp_path / "riffle", name="default-cards.json", updated_at=None)
    stamp = datetime(2026, 3, 4, 12, tzinfo=UTC).timestamp()
    os.utime(bulk, (stamp, stamp))
    assert scryfall.bulk_day(bulk) == date(2026, 3, 4)
    path, written = scryfall.snapshot_prices()
    assert written and path.name == "2026-03-04.jsonl.gz" and len(snapshot_lines(path)) == 2


def test_snapshot_needs_a_bulk_file(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    with pytest.raises(FileNotFoundError):
        scryfall.snapshot_prices()
    (tmp_path / "riffle").mkdir()
    (tmp_path / "riffle" / "default-cards.jsonl.gz.part").write_bytes(b"")  # a half download doesn't count
    assert scryfall.bulk_file() is None


# ---- refresh --------------------------------------------------------------------


def test_refresh_reports_the_download_and_the_load(tmp_path, monkeypatch, tracker):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    bulk = tmp_path / "riffle" / "default-cards.jsonl.gz"  # download() writes into the data folder
    bulk.parent.mkdir()
    bulk.write_bytes(b"x" * 2_500_000)

    def download(progress):
        progress(2_500_000, 2_500_000)
        return bulk, {"updated_at": "2026-09-24T21:05:23.456+00:00"}

    monkeypatch.setattr(scryfall, "download", download)
    monkeypatch.setattr(scryfall, "load", lambda path: 118_389)
    scryfall.refresh(force=True, tracker=tracker)
    assert tracker.outcomes() == {
        "Scryfall bulk data": ("ok", "2.5 MB, Scryfall 2026-09-24"),
        "card catalog": ("ok", "118,389 printings"),
    }
    assert tracker.steps[0].unit == "bytes" and tracker.steps[0].updates == [(2_500_000, 2_500_000)]
    assert json.loads(scryfall.meta_path().read_text())["rows"] == 118_389


def test_refresh_reports_a_failed_download_then_raises(tmp_path, monkeypatch, tracker):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    def download(progress):
        raise net.FetchError("HTTP 503")

    monkeypatch.setattr(scryfall, "download", download)
    with pytest.raises(net.FetchError):
        scryfall.refresh(force=True, tracker=tracker)
    assert tracker.outcomes() == {"Scryfall bulk data": ("fail", "HTTP 503")}


def test_refresh_skips_a_recent_load(monkeypatch, tracker):
    monkeypatch.setattr(scryfall, "is_stale", lambda max_age_hours: False)
    scryfall.refresh(tracker=tracker)
    assert tracker.outcomes() == {"Scryfall bulk data": ("ok", "current")}
