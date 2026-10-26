from types import SimpleNamespace

from zlapi import Message, ZaloAPI
from zlapi.models import ThreadType


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


def _client():
    client = object.__new__(ZaloAPI)
    client._imei = "test-imei"
    client.user_id = "42"
    client._encode = lambda value: value
    client._decode = lambda value: value
    return client


def test_group_send_response_without_cli_id_gets_request_client_id(monkeypatch):
    client = _client()
    captured = {}
    monkeypatch.setattr("zlapi._client._util.now", lambda: 123456)
    client._post = lambda url, params, data: captured.update(data=data) or _Response(
        {"error_code": 0, "data": {"msgId": "global-1"}}
    )

    result = client.sendMessage(Message(text="hello"), "987", ThreadType.GROUP)

    assert captured["data"]["params"]["clientId"] == 123456
    assert result.msgId == "global-1"
    assert result.cliMsgId == "123456"
    client.fetchAllGroups = lambda: (_ for _ in ()).throw(AssertionError("Unexpected group lookup"))
    assert client._pins()._resolve_thread("987", None) == ("987", ThreadType.GROUP)
