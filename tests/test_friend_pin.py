import copy
import json
import struct
from types import SimpleNamespace

import pytest

from zlapi import ZaloAPI
from zlapi.models import EventType, GroupEventType, MessageObject, ThreadType, User, ZaloAPIException, ZaloUserError


def client_with_response(result, outer_error=0):
    client = ZaloAPI(auto_login=False)
    client.user_id = "42"
    client._imei = "test-imei"
    calls = []
    client._encode = lambda data: "encrypted:" + json.dumps(data)
    client._decode = lambda data: json.loads(data)
    def get(url, params):
        calls.append((url, json.loads(params["params"][len("encrypted:"):]), params))
        return SimpleNamespace(json=lambda: {"error_code": outer_error, "error_message": "test error", "data": json.dumps(result)})
    client._get = get
    return client, calls


def topic(id="pin-1", **extra):
    return {"id": id, "type": 2, "params": json.dumps({"global_msg_id": "m1", "title": "hello"}), **extra}


def message(msg_type="webchat"):
    content = "hello"
    if msg_type != "webchat":
        content = {"thumb": "thumb", "description": "description", "title": "title", "id": 1,
                   "catId": 2, "type": 3, "href": "https://example.com", "action": "action", "params": "{}"}
    return MessageObject.fromDict({"msgType": msg_type, "msgId": "m1", "cliMsgId": "c1",
                                   "uidFrom": "0", "dName": "Tester", "content": content}, None)


def test_create_payload_and_version_survive_envelope():
    api, calls = client_with_response({"error_code": 0, "data": {"data": json.dumps(topic()), "version": 9}})
    result = api.pinUserMsg(message(), "123", version=8)
    url, payload, query = calls[0]
    assert url.endswith("/api/friendboard/create")
    assert payload["conversationId"] == "123"
    assert payload["version"] == 8
    assert payload["lang"] == "vi"
    assert "grid" not in payload
    assert payload["topic"]["duration"] == 0
    assert payload["topic"]["pinAct"] == 1
    assert payload["topic"]["src"] == -1
    assert payload["topic"]["imei"] == "test-imei"
    assert json.loads(payload["topic"]["params"])["senderUid"] == "42"
    assert query["zpw_ver"] and query["zpw_type"]
    assert isinstance(result, User)
    assert result.version == 9
    assert result.data.id == "pin-1"
    assert result.data.params.title == "hello"


@pytest.mark.parametrize("msg_type", ["webchat", "chat.voice", "chat.photo", "chat.video.msg", "chat.sticker",
                                     "chat.recommended", "chat.link", "chat.location.new", "share.file", "chat.gif"])
def test_supported_media_share_group_serialization(msg_type):
    api, calls = client_with_response({"data": topic(), "version": 1})
    group_calls = []
    api._post = lambda url, params, data: group_calls.append(json.loads(data["params"][len("encrypted:"):])) or SimpleNamespace(
        json=lambda: {"error_code": 0, "data": json.dumps({"id": "group-pin"})})
    api.pinGroupMsg(message(msg_type), "987")
    api.pinUserMsg(message(msg_type), "123")
    group_payload = group_calls[0]
    assert group_payload["grid"] == "987"
    assert "src" not in group_payload
    assert group_payload["params"] == calls[0][1]["topic"]["params"]


def test_list_decodes_filters_and_preserves_server_order():
    api, calls = client_with_response({"error_code": 0, "data": {"data": [
        json.dumps(topic("first", createTime=1)), {"id": "note", "type": 1}, topic("second", createTime=999)
    ], "version": 9}})
    result = api.getUserPinMsg(123)
    assert [pin.id for pin in result.data] == ["first", "second"]
    assert result.data[0].params.global_msg_id == "m1"
    assert result.version == 9
    assert api.getLatestUserPinMsg(123).id == "first"
    assert calls[0][1] == {"conversationId": "123", "version": 0}
    assert calls[0][0].endswith("/friendboard/list")


def test_empty_list_is_success_and_latest_is_none():
    api, _ = client_with_response({"data": [], "version": 0})
    assert api.getUserPinMsg("123").data == []
    assert api.getLatestUserPinMsg("123") is None


def test_unpin_uses_board_version_and_topic_id():
    api, calls = client_with_response({"version": 101})
    assert api.unpinUserMsg("pin-1", "100", "123").version == 101
    assert calls[0][0].endswith("/friendboard/multi_unpin")
    assert calls[0][1] == {"conversationId": "123", "topics": [{"topicId": "pin-1", "topicType": 2}], "version": 100, "lang": "vi"}


@pytest.mark.parametrize("result,outer", [({}, 12), ({"error_code": 13, "error_message": "stale"}, 0),
    ({"error_code": 0, "data": {"error_code": 14, "error_message": "nested"}}, 0),
    (None, 0), ({"data": "bad json", "version": 1}, 0), ({"data": {}, "version": 1}, 0)])
def test_response_errors_are_not_silently_empty_lists(result, outer):
    api, _ = client_with_response(result, outer)
    with pytest.raises(ZaloAPIException):
        api.getUserPinMsg("123")


@pytest.mark.parametrize("value", [None, "", "0", False])
def test_invalid_id_fails_before_network(value):
    api, calls = client_with_response({})
    with pytest.raises(ZaloUserError):
        api.getUserPinMsg(value)
    assert not calls


@pytest.mark.parametrize("value", [None, -1, "bad", 1.5, True])
def test_invalid_version_fails_before_network(value):
    api, calls = client_with_response({})
    with pytest.raises(ZaloUserError):
        api.unpinUserMsg("pin-1", value, "123")
    assert not calls


def test_unsupported_message_fails_before_network():
    api, calls = client_with_response({})
    with pytest.raises(ZaloUserError):
        api.pinUserMsg(message("unknown"), "123")
    assert not calls


def control(act="pin_create", actor="42", encoded=True):
    data = {"conversationId": "123", "actorId": actor, "version": 10, "oldVersion": 9,
            "topic": topic() if act == "pin_create" else {"topicId": "pin-1", "topicType": 2}}
    return {"msgId": "control-1", "content": {"act_type": "fr", "act": act, "data": json.dumps(data) if encoded else data}}


@pytest.mark.parametrize("threaded", [False, True])
@pytest.mark.parametrize("act,event_type", [("pin_create", EventType.NEW_PIN_TOPIC), ("pin_unpin", EventType.UNPIN_TOPIC)])
@pytest.mark.parametrize("actor,encoded", [("42", True), ("123", False)])
def test_pin_controls_reach_on_message_only(monkeypatch, threaded, act, event_type, actor, encoded):
    api = ZaloAPI(auto_login=False)
    api.thread = threaded
    received, events, errors, submissions = [], [], [], []
    api.onMessage = lambda *args: received.append(args)
    api.onEvent = lambda *args: events.append(args)
    api.onErrorCallBack = errors.append
    def submit(fn, *args):
        submissions.append(fn)
        fn(*args)
    monkeypatch.setattr("zlapi._client.pool.submit", submit)
    raw = control(act, actor, encoded)
    original = copy.deepcopy(raw)
    api._handle_ws_controls([raw])
    assert len(received) == 1
    mid, author, data, obj, thread_id, thread_type = received[0]
    assert (mid, author, thread_id, thread_type) == ("control-1", actor, "123", ThreadType.USER)
    assert obj.event_type == event_type
    assert obj.event_data is data
    assert obj.content == raw["content"]
    assert raw == original
    assert data.version == 10
    if act == "pin_create":
        assert data.topic.params.title == "hello"
    else:
        assert data.topic.topicId == "pin-1"
    assert bool(submissions) == threaded
    assert not events and not errors


def test_bad_controls_do_not_drop_following_events_and_groups_still_work():
    api = ZaloAPI(auto_login=False)
    api.thread = False
    received, events, errors = [], [], []
    api.onMessage = lambda *args: received.append(args)
    api.onEvent = lambda *args: events.append(args)
    api.onErrorCallBack = errors.append
    missing_mid = control()
    del missing_mid["msgId"]
    malformed = control()
    malformed["content"]["data"] = "{broken"
    api._handle_ws_controls([
        missing_mid, malformed,
        {"content": {"act_type": "fr", "act": "req", "data": "ignored"}},
        {"content": {"act_type": "group", "act": "join_reject", "data": "ignored"}},
        {"content": {"act_type": "group", "act": "new_pin_topic", "data": '{"groupId":"987"}'}},
        control("pin_unpin"),
    ])
    assert len(received) == 2 and received[0][0] is None
    assert len(errors) == 1
    assert len(events) == 1 and events[0][1] == GroupEventType.NEW_PIN_TOPIC


def test_listener_routes_wire_controls_and_ordinary_messages(monkeypatch):
    api = ZaloAPI(cookies={"session": "test"}, auto_login=False)
    api._state._config["zpw_ws"] = ["wss://example.invalid"]
    api.user_id = "42"
    api.ws_key = "test-key"
    received, errors = [], []
    api.onMessage = lambda *args: received.append(args)
    api.onErrorCallBack = errors.append
    unpin = control("pin_unpin")
    unpin["content"]["data"] = json.dumps({
        "topic": {"topicId": 12345, "topicType": 2},
        "actorId": "42", "conversationId": "123", "oldVersion": 9, "version": 10,
    })

    class Socket:
        def __init__(self, url, **callbacks):
            self.receive = callbacks["on_message"]

        def run_forever(self, **kwargs):
            # Exercise the real header parser, decoder and listener dispatcher.
            for cmd, data in [
                (501, {"msgs": [{"msgId": "m1", "uidFrom": "123", "idTo": "0",
                                 "msgType": "webchat", "content": "normal message"}]}),
                (601, {"controls": [control(), {"content": None}, unpin]}),
            ]:
                payload = {"encrypt": 0, "data": json.dumps({"data": data})}
                self.receive(self, struct.pack("<BHB", 1, cmd, 0) + json.dumps(payload).encode())

    monkeypatch.setattr("zlapi._client.websocket.WebSocketApp", Socket)
    api.listen()
    assert received[0][2] == "normal message"
    assert received[1][3].event_type == EventType.NEW_PIN_TOPIC
    assert received[2][3].event_type == EventType.UNPIN_TOPIC
    assert received[2][2].topic.topicId == 12345
    assert len(errors) == 1
