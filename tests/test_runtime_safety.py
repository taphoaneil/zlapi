from types import SimpleNamespace

import pytest
from PIL import Image

from zlapi import ZaloAPI, ZaloSessionKicked
from zlapi._state import State
from zlapi.models import ThreadType


def test_request_timeout_defaults_can_be_overridden_or_disabled():
    calls = []
    state = State(request_timeout=(10, 60))
    state._session = SimpleNamespace(get=lambda *args, **kwargs: calls.append(kwargs))

    state._get("https://api.example")
    state._get("https://api.example", timeout=3)
    state._request_timeout = None
    state._get("https://api.example")

    assert [call["timeout"] for call in calls] == [(10, 60), 3, None]


def test_login_uses_its_own_default_timeout(monkeypatch):
    calls = []
    response = SimpleNamespace(
        json=lambda: {
            "data": {
                "uid": "account-1",
                "send2me_id": "cloud-1",
                "phone_number": "",
                "zpw_enk": "secret",
                "zpw_ws": ["wss://example"],
            }
        }
    )
    monkeypatch.setattr("zlapi._state.requests.get", lambda *args, **kwargs: calls.append(kwargs) or response)
    state = State(login_timeout=None)
    state.set_cookies({"session": "test"})

    state.login(None, None, "imei")

    assert calls[0]["timeout"] is None


def test_album_send_is_attempted_once_after_ambiguous_failure(tmp_path):
    paths = [tmp_path / "one.webp", tmp_path / "two.webp"]
    for path in paths:
        Image.new("RGB", (40, 40), "white").save(path)

    client = ZaloAPI(auto_login=False)
    uploads = []
    sends = []
    client._uploadImage = lambda path, *_args: uploads.append(path) or {
        "normalUrl": "https://cdn.example/image.webp",
        "thumbUrl": "https://cdn.example/thumb.webp",
        "hdUrl": "https://cdn.example/hd.webp",
    }
    client._buildMultiLocalImagePayload = lambda *_args: {"params": {}}

    def send(*_args, **_kwargs):
        sends.append(True)
        raise TimeoutError("response lost after provider acceptance")

    client.sendLocalImage = send
    result = client.sendMultiLocalImage(paths, "destination", ThreadType.USER)

    assert len(uploads) == 2
    assert len(sends) == 1
    assert [(failure.index, failure.stage) for failure in result.failed] == [(0, "send"), (1, "send")]
    assert "Not attempted" in result.failed[1].error


def test_custom_ping_scheduler_is_used_and_cancelled():
    scheduled = []

    class Handle:
        cancelled = False

        def cancel(self):
            self.cancelled = True

    def scheduler(delay, callback):
        handle = Handle()
        scheduled.append((delay, callback, handle))
        return handle

    client = ZaloAPI(auto_login=False, ping_scheduler=scheduler)
    client.ws = SimpleNamespace(send=lambda *_args: None)
    client.ws_ping_scheduler()
    client._cancel_ping_schedule()

    assert scheduled[0][0] == 180
    assert scheduled[0][2].cancelled is True


def test_default_ping_scheduler_creates_daemon_timer():
    handle = ZaloAPI._schedule_daemon_timer(60, lambda: None)
    try:
        assert handle.daemon is True
    finally:
        handle.cancel()


def test_listener_reports_session_kick_without_signalling_process(monkeypatch):
    callbacks = {}
    errors = []

    class FakeWebSocket:
        closed = False

        def close(self):
            self.closed = True

        def run_forever(self, **_kwargs):
            callbacks["on_message"](self, bytes([1, 0xB8, 0x0B, 0]) + b"{}")

    def websocket_app(*_args, **kwargs):
        callbacks.update(kwargs)
        return FakeWebSocket()

    monkeypatch.setattr("zlapi._client.websocket.WebSocketApp", websocket_app)
    monkeypatch.setattr("zlapi._client._util.zws_decode", lambda *_args: {"data": {}})
    client = ZaloAPI(auto_login=False)
    client._state._config["zpw_ws"] = ["wss://example"]
    client._state.set_cookies({"session": "test"})
    client.ws_key = "key"
    client.onErrorCallBack = errors.append

    client._listen()

    assert len(errors) == 1
    assert isinstance(errors[0], ZaloSessionKicked)


def test_listener_reports_keyboard_interrupt_without_signalling_process(monkeypatch):
    callbacks = {}
    errors = []

    class FakeWebSocket:
        def close(self):
            pass

        def run_forever(self, **_kwargs):
            callbacks["on_error"](self, KeyboardInterrupt())

    def websocket_app(*_args, **kwargs):
        callbacks.update(kwargs)
        return FakeWebSocket()

    monkeypatch.setattr("zlapi._client.websocket.WebSocketApp", websocket_app)
    client = ZaloAPI(auto_login=False)
    client._state._config["zpw_ws"] = ["wss://example"]
    client._state.set_cookies({"session": "test"})
    client.onErrorCallBack = errors.append

    client._listen()

    assert len(errors) == 1
    assert isinstance(errors[0], KeyboardInterrupt)
