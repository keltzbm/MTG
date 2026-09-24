from datetime import date
from pathlib import Path

import pytest

from riffle import net
from riffle.ingest import tcgcsv

ARCHIVE = tcgcsv.SEVEN_ZIP_MAGIC + b"payload"


def fake_download(answers: dict[str, bytes | None | Exception]):
    """answers: url -> file bytes, None (404), or an exception to raise. Records every url asked for."""
    asked: list[str] = []

    def download(url: str, dest: Path, progress) -> int | None:
        asked.append(url)
        answer = answers.get(url)
        if isinstance(answer, Exception):
            raise answer
        if answer is None:
            return None
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(answer)
        if progress:
            progress(len(answer), len(answer))
        return len(answer)

    return download, asked


def store(day: date, data: bytes = ARCHIVE) -> None:
    tcgcsv.archive_path(day).parent.mkdir(parents=True, exist_ok=True)
    tcgcsv.archive_path(day).write_bytes(data)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(tcgcsv.time, "sleep", lambda _: None)


def test_urls_and_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    d = date(2026, 9, 21)
    assert tcgcsv.archive_url(d) == "https://tcgcsv.com/archive/tcgplayer/prices-2026-09-21.ppmd.7z"
    assert tcgcsv.archive_path(d) == tmp_path / "riffle" / "tcgcsv" / "archive" / "prices-2026-09-21.ppmd.7z"


def test_fetches_missing_days_and_stores_them_as_downloaded(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    d1, d2 = date(2026, 9, 20), date(2026, 9, 21)
    download, asked = fake_download({tcgcsv.archive_url(d1): ARCHIVE, tcgcsv.archive_url(d2): ARCHIVE})
    res = tcgcsv.ingest(d1, d2, download=download)
    assert res.fetched == [d1, d2]
    assert tcgcsv.archive_path(d1).read_bytes() == ARCHIVE
    assert tcgcsv.stored_days() == [d1, d2]
    assert tcgcsv.stored_bytes() == 2 * len(ARCHIVE)
    assert len(asked) == 2


def test_stored_days_are_skipped_without_a_request(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    d1, d2 = date(2026, 9, 20), date(2026, 9, 21)
    store(d1)
    download, asked = fake_download({tcgcsv.archive_url(d2): ARCHIVE})
    res = tcgcsv.ingest(d1, d2, download=download)
    assert res.skipped == 1
    assert res.fetched == [d2]
    assert asked == [tcgcsv.archive_url(d2)]


def test_unpublished_day_is_pending_and_not_stored(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    d = date(2026, 9, 22)
    download, _ = fake_download({tcgcsv.archive_url(d): None})
    res = tcgcsv.ingest(d, d, download=download)
    assert res.pending == [d]
    assert tcgcsv.stored_days() == []


def test_failed_day_is_reported_and_the_run_continues(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    d1, d2 = date(2026, 9, 20), date(2026, 9, 21)
    download, _ = fake_download(
        {tcgcsv.archive_url(d1): net.FetchError("HTTP 503"), tcgcsv.archive_url(d2): ARCHIVE}
    )
    res = tcgcsv.ingest(d1, d2, download=download)
    assert res.failed == [(d1, "HTTP 503")]
    assert res.fetched == [d2]


def test_non_7z_download_is_rejected_and_nothing_is_written(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    d = date(2026, 9, 21)
    download, _ = fake_download({tcgcsv.archive_url(d): b"<html>maintenance</html>"})
    res = tcgcsv.ingest(d, d, download=download)
    assert [day for day, _ in res.failed] == [d]
    assert not tcgcsv.store_dir().exists() or not any(tcgcsv.store_dir().iterdir())


def test_start_is_clamped_to_the_first_archived_day(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    download, asked = fake_download({})
    tcgcsv.ingest(date(2023, 1, 1), date(2024, 2, 9), download=download)
    assert asked == [tcgcsv.archive_url(date(2024, 2, 8)), tcgcsv.archive_url(date(2024, 2, 9))]


def test_requests_are_paced_but_not_before_the_first(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    sleeps: list[float] = []
    monkeypatch.setattr(tcgcsv.time, "sleep", sleeps.append)
    download, _ = fake_download({})
    tcgcsv.ingest(date(2026, 9, 19), date(2026, 9, 21), delay=0.5, download=download)
    assert sleeps == [0.5, 0.5]


def test_unrelated_files_in_the_archive_folder_are_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    store(date(2026, 9, 21))
    (tcgcsv.store_dir() / "prices-garbage.ppmd.7z").write_bytes(ARCHIVE)
    (tcgcsv.store_dir() / "prices-2026-09-22.ppmd.7z.part").write_bytes(b"half")
    assert tcgcsv.stored_days() == [date(2026, 9, 21)]


def test_meter_gets_the_day_and_byte_counts(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    d = date(2026, 9, 21)
    download, _ = fake_download({tcgcsv.archive_url(d): ARCHIVE})
    seen = []
    tcgcsv.ingest(d, d, download=download, meter=lambda day, done, total: seen.append((day, done, total)))
    assert seen == [(d, len(ARCHIVE), len(ARCHIVE))]


def test_rejected_download_leaves_nothing_stored(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    d = date(2026, 9, 21)
    download, _ = fake_download({tcgcsv.archive_url(d): b"<html>maintenance</html>"})
    res = tcgcsv.ingest(d, d, download=download)
    assert not tcgcsv.archive_path(d).exists()
    assert "7z" in res.failed[0][1]
