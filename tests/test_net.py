"""riffle.net against a fake urlopen: retries, rate limits, 404s, and streamed downloads."""

import io
import urllib.error

import pytest

from riffle import net


class Resp(io.BytesIO):
    """A response: readable in chunks, usable in `with`, with headers."""

    def __init__(self, body: bytes, length: bool = True):
        super().__init__(body)
        self.headers = {"Content-Length": str(len(body))} if length else {}


def http_error(code: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    headers = {"Retry-After": retry_after} if retry_after else {}
    return urllib.error.HTTPError("https://example.test", code, "x", headers, None)


@pytest.fixture
def server(monkeypatch):
    """Answers queued per test; records every request and every sleep."""
    state = {"answers": [], "requests": [], "sleeps": []}

    def urlopen(req, timeout):
        state["requests"].append(req)
        answer = state["answers"].pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    monkeypatch.setattr(net.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(net.time, "sleep", state["sleeps"].append)
    return state


def test_every_request_identifies_the_tool(server):
    server["answers"] = [Resp(b"ok")]
    net.get("https://example.test", accept="application/json")
    req = server["requests"][0]
    ua = req.get_header("User-agent")
    assert ua.startswith("riffle/") and "github.com/keltzbm/riffle" in ua
    assert req.get_header("Accept") == "application/json"


def test_stalls_are_retried_with_growing_waits(server):
    server["answers"] = [TimeoutError("slow"), TimeoutError("slow"), Resp(b"ok")]
    assert net.get_text("https://example.test") == "ok"
    assert server["sleeps"] == [2.0, 4.0]


def test_gives_up_after_the_last_retry(server):
    server["answers"] = [urllib.error.URLError("down")] * 3
    with pytest.raises(net.FetchError, match="no answer after 3 tries"):
        net.get("https://example.test")
    assert len(server["requests"]) == 3


def test_rate_limit_waits_for_retry_after(server):
    server["answers"] = [http_error(429, retry_after="7"), Resp(b"ok")]
    assert net.get("https://example.test") == b"ok"
    assert server["sleeps"] == [7.0]


def test_rate_limit_without_retry_after_uses_the_backoff(server):
    server["answers"] = [http_error(429, retry_after="Wed, 21 Oct 2026 07:28:00 GMT"), Resp(b"ok")]
    assert net.get("https://example.test") == b"ok"
    assert server["sleeps"] == [2.0]


def test_404_is_an_answer_not_a_failure(server):
    server["answers"] = [http_error(404)]
    assert net.get("https://example.test") is None
    assert server["sleeps"] == []


def test_get_text_treats_404_as_an_error(server):
    server["answers"] = [http_error(404)]
    with pytest.raises(net.FetchError, match="HTTP 404"):
        net.get_text("https://example.test")


def test_client_errors_are_not_retried(server):
    server["answers"] = [http_error(403)]
    with pytest.raises(net.FetchError, match="HTTP 403"):
        net.get("https://example.test")
    assert len(server["requests"]) == 1


def test_download_streams_in_chunks_and_reports_progress(server, tmp_path, monkeypatch):
    monkeypatch.setattr(net, "CHUNK", 4)
    server["answers"] = [Resp(b"0123456789")]
    seen = []
    dest = tmp_path / "sub" / "file.bin"
    assert net.download("https://example.test", dest, progress=lambda d, t: seen.append((d, t))) == 10
    assert dest.read_bytes() == b"0123456789"
    assert seen == [(4, 10), (8, 10), (10, 10)]
    assert not (tmp_path / "sub" / "file.bin.part").exists()


def test_download_without_content_length_reports_unknown_total(server, tmp_path):
    server["answers"] = [Resp(b"abc", length=False)]
    seen = []
    net.download("https://example.test", tmp_path / "f", progress=lambda d, t: seen.append(t))
    assert seen == [None]


def test_interrupted_download_leaves_no_file(server, tmp_path):
    class Dropped(Resp):
        def read(self, n=-1):
            raise ConnectionResetError("reset")

    server["answers"] = [Dropped(b"")]
    dest = tmp_path / "f"
    with pytest.raises(net.FetchError, match="interrupted"):
        net.download("https://example.test", dest)
    assert not dest.exists() and not (tmp_path / "f.part").exists()


def test_download_404_writes_nothing(server, tmp_path):
    server["answers"] = [http_error(404)]
    assert net.download("https://example.test", tmp_path / "f") is None
    assert list(tmp_path.iterdir()) == []
