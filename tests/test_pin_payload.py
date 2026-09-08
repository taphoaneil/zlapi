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


def test_pin_group_message_uses_current_minimum_board_fields():
    client = _client()
    captured = {}
    client._post = lambda url, params, data: captured.update(url=url, params=params, data=data) or _Response(
        {"error_code": 0, "data": {"id": "board-1"}}
    )

    client.pinGroupMsg(
        SimpleNamespace(
            msgType="webchat",
            msgId="global-1",
            cliMsgId="client-1",
            uidFrom="42",
            dName="Tester",
            content="List Acc 08/09 ae xem từ đây ⬇️ nhé!",
        ),
        "987",
    )

    params = captured["data"]["params"]
    assert params["grid"] == "987"
    assert params["type"] == 2
    assert params["color"] == -14540254
    assert params["emoji"] == "📌"
    assert params["duration"] == 0
    assert params["imei"] == "test-imei"
    assert params["pinAct"] == 1
    for obsolete in ("startTime", "repeat", "src"):
        assert obsolete not in params


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
