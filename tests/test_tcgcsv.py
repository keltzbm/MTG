from datetime import date

import pytest

from mtg.ingest import tcgcsv

ARCHIVE = tcgcsv.SEVEN_ZIP_MAGIC + b"payload"


def fake_get(answers: dict[str, bytes | None | Exception]):
    """answers: url -> bytes, None (404), or an exception to raise. Records every url asked for."""
    asked: list[str] = []

    def get(url: str) -> bytes | None:
        asked.append(url)
        answer = answers.get(url)
        if isinstance(answer, Exception):
            raise answer
        return answer

    return get, asked


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(tcgcsv.time, "sleep", lambda _: None)


def test_urls_and_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    d = date(2026, 9, 21)
    assert tcgcsv.archive_url(d) == "https://tcgcsv.com/archive/tcgplayer/prices-2026-09-21.ppmd.7z"
    assert tcgcsv.archive_path(d) == tmp_path / "mtg" / "tcgcsv" / "archive" / "prices-2026-09-21.ppmd.7z"


def test_fetches_missing_days_and_stores_them_as_downloaded(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    d1, d2 = date(2026, 9, 20), date(2026, 9, 21)
    get, asked = fake_get({tcgcsv.archive_url(d1): ARCHIVE, tcgcsv.archive_url(d2): ARCHIVE})
    res = tcgcsv.ingest(d1, d2, get=get)
    assert res.fetched == [d1, d2]
    assert tcgcsv.archive_path(d1).read_bytes() == ARCHIVE
    assert tcgcsv.stored_days() == [d1, d2]
    assert tcgcsv.stored_bytes() == 2 * len(ARCHIVE)
    assert len(asked) == 2


def test_stored_days_are_skipped_without_a_request(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    d1, d2 = date(2026, 9, 20), date(2026, 9, 21)
    tcgcsv.save(d1, ARCHIVE)
    get, asked = fake_get({tcgcsv.archive_url(d2): ARCHIVE})
    res = tcgcsv.ingest(d1, d2, get=get)
    assert res.skipped == 1
    assert res.fetched == [d2]
    assert asked == [tcgcsv.archive_url(d2)]


def test_unpublished_day_is_pending_and_not_stored(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    d = date(2026, 9, 22)
    get, _ = fake_get({tcgcsv.archive_url(d): None})
    res = tcgcsv.ingest(d, d, get=get)
    assert res.pending == [d]
    assert tcgcsv.stored_days() == []


def test_failed_day_is_reported_and_the_run_continues(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    d1, d2 = date(2026, 9, 20), date(2026, 9, 21)
    get, _ = fake_get(
        {tcgcsv.archive_url(d1): tcgcsv.FetchError("HTTP 503"), tcgcsv.archive_url(d2): ARCHIVE}
    )
    res = tcgcsv.ingest(d1, d2, get=get)
    assert res.failed == [(d1, "HTTP 503")]
    assert res.fetched == [d2]


def test_non_7z_download_is_rejected_and_nothing_is_written(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    d = date(2026, 9, 21)
    get, _ = fake_get({tcgcsv.archive_url(d): b"<html>maintenance</html>"})
    res = tcgcsv.ingest(d, d, get=get)
    assert [day for day, _ in res.failed] == [d]
    assert not tcgcsv.store_dir().exists() or not any(tcgcsv.store_dir().iterdir())


def test_start_is_clamped_to_the_first_archived_day(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    get, asked = fake_get({})
    tcgcsv.ingest(date(2023, 1, 1), date(2024, 2, 9), get=get)
    assert asked == [tcgcsv.archive_url(date(2024, 2, 8)), tcgcsv.archive_url(date(2024, 2, 9))]


def test_requests_are_paced_but_not_before_the_first(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    sleeps: list[float] = []
    monkeypatch.setattr(tcgcsv.time, "sleep", sleeps.append)
    get, _ = fake_get({})
    tcgcsv.ingest(date(2026, 9, 19), date(2026, 9, 21), delay=0.5, get=get)
    assert sleeps == [0.5, 0.5]


def test_unrelated_files_in_the_archive_folder_are_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    tcgcsv.save(date(2026, 9, 21), ARCHIVE)
    (tcgcsv.store_dir() / "prices-garbage.ppmd.7z").write_bytes(ARCHIVE)
    (tcgcsv.store_dir() / "prices-2026-09-22.ppmd.7z.part").write_bytes(b"half")
    assert tcgcsv.stored_days() == [date(2026, 9, 21)]


def test_404_returns_none_and_other_http_errors_retry_then_raise(monkeypatch):
    import urllib.error

    calls = []

    def fake_urlopen(req, timeout):
        calls.append(req.full_url)
        code = 404 if "404" in req.full_url else 503
        raise urllib.error.HTTPError(req.full_url, code, "x", {}, None)

    monkeypatch.setattr(tcgcsv.urllib.request, "urlopen", fake_urlopen)
    assert tcgcsv._get("https://example.test/404") is None
    assert len(calls) == 1
    with pytest.raises(tcgcsv.FetchError, match="HTTP 503"):
        tcgcsv._get("https://example.test/503", retries=2)
    assert len(calls) == 4


def test_user_agent_identifies_the_tool():
    assert tcgcsv.HEADERS["User-Agent"].startswith("keltzbm-mtg/")
