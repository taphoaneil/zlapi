import json
from types import SimpleNamespace

import pytest

from zlapi import ZaloAPI
from zlapi._exception import ZaloAPIException, ZaloUserError
from zlapi.models import MessageObject, PinEventType, ThreadType


class Response:
    def __init__(self, value): self.value = value
    def json(self): return self.value


def api_with_friend(result):
    api = ZaloAPI(auto_login=False)
    api.user_id, api._imei = "42", "imei"
    api._encode = lambda value: json.dumps(value)
    api._decode = lambda value: json.loads(value) if isinstance(value, str) else value
    calls = []
    def get(url, params):
        calls.append((url, json.loads(params["params"])))
        return Response({"error_code": 0, "data": json.dumps(result)})
    api._get = get
    api.fetchAllGroups = lambda: {"gridVerMap": {}}
    return api, calls


def topic(pin_id="pin-1"):
    return {"id": pin_id, "type": 2, "params": json.dumps({"global_msg_id": "m1", "client_msg_id": "c1", "title": "hello"})}


def message():
    return MessageObject.fromDict({"msgType": "webchat", "msgId": "m1", "cliMsgId": "c1", "uidFrom": "42", "dName": "A", "content": "hello"}, None)


def test_common_friend_list_and_unpin_hide_version():
    api, calls = api_with_friend({"data": [topic()], "version": 9})
    pins = api.getPinnedMessages("123")
    assert pins[0].id == "pin-1"
    assert pins[0].message_id == "m1"
    def after_list(url, params):
        calls.append((url, json.loads(params["params"])))
        body = {"data": [topic()], "version": 9} if url.endswith("/list") else {"version": 10}
        return Response({"error_code": 0, "data": json.dumps(body)})
    api._get = after_list
    result = api.unpinMessage("pin-1", "123")
    assert result.removed_ids == ["pin-1"]
    assert calls[-1][1]["version"] == 9


def test_cloud_rejected_and_event_uses_common_callback():
    api, _ = api_with_friend({"data": [], "version": 0})
    try:
        api.getPinnedMessages("cloud", ThreadType.CLOUD)
    except Exception as error:
        assert "CLOUD" in str(error)
    else:
        assert False
    received = []
    api.onPinEvent = received.append
    api.onErrorCallBack = lambda error: (_ for _ in ()).throw(error)
    api._handle_ws_controls([{"content": {"act_type": "fr", "act": "pin_create", "data": json.dumps({"conversationId": "123", "actorId": "42", "topic": topic()})}}])
    assert received[0].type == PinEventType.CREATED
    assert received[0].pins[0].id == "pin-1"


def test_group_uses_the_same_public_api():
    api = ZaloAPI(auto_login=False)
    api.user_id, api._imei = "42", "imei"
    api._encode = lambda value: value
    api._decode = lambda value: value
    group_topic = topic("group-pin"); group_topic["createTime"] = 7
    api._get = lambda *args, **kwargs: Response({"error_code": 0, "data": {
        "error_code": 0, "data": {"boardVersion": 7, "items": [group_topic]}}})
    pins = api.getPinnedMessages("987", ThreadType.GROUP)
    assert pins[0].thread_type == ThreadType.GROUP
    assert pins[0].id == "group-pin"


# Exercise every public operation against both transports with no thread_type.
@pytest.mark.parametrize("thread_type", [ThreadType.USER, ThreadType.GROUP])
@pytest.mark.parametrize("operation", ["create", "list", "remove", "remove_all"])
def test_auto_routing_for_all_pin_operations(thread_type, operation):
    api = ZaloAPI(auto_login=False)
    api.user_id, api._imei = "42", "imei"
    api._encode = lambda value: value
    api._decode = lambda value: value
    lookups, calls = [], []
    def groups():
        lookups.append(True)
        return SimpleNamespace(toDict=lambda: {"gridVerMap": {"987": 1} if thread_type == ThreadType.GROUP else {}})
    api.fetchAllGroups = groups
    items = [topic()]
    def friend(action, payload):
        calls.append(("friend", action, payload))
        if action == "create":
            return {"data": topic(), "version": 7}
        if action == "multi_unpin":
            items.clear()
        return {"data": list(items), "version": 7}
    api._friend_board_request = friend
    def get(url, params):
        calls.append(("group", url, params["params"]))
        if url.endswith("/unpinv2"):
            items.clear()
        return Response({"error_code": 0, "data": {"error_code": 0, "data": {
            "items": list(items), "boardVersion": 7}}})
    def post(url, params, data):
        calls.append(("group", url, data["params"]))
        return Response({"error_code": 0, "data": {}})
    api._get, api._post = get, post
    if operation == "create":
        result = api.pinMessage(message(), "987")
        assert result.id == "pin-1"
        assert result.thread_type == thread_type
    elif operation == "list":
        result = api.getPinnedMessages("987")
        assert result[0].thread_type == thread_type
    elif operation == "remove":
        result = api.unpinMessage("pin-1", "987")
        assert result.removed_ids == ["pin-1"]
    else:
        result = api.unpinAllMessages("987")
        assert result.removed_ids == ["pin-1"]
    assert lookups == [True]
    expected = "group" if thread_type == ThreadType.GROUP else "friend"
    assert calls and all(call[0] == expected for call in calls)
    if thread_type == ThreadType.GROUP:
        expected_endpoint = {"create": "/topic/createv2", "list": "/pin/list",
                             "remove": "/unpinv2", "remove_all": "/unpinv2"}[operation]
        assert any(call[1].endswith(expected_endpoint) for call in calls)
    # The resolved type is reused for subsequent calls in this session.
    api.getPinnedMessages("987")
    assert lookups == [True]


def test_incoming_context_is_known_before_callback():
    api = ZaloAPI(auto_login=False)
    api.thread = False
    api.fetchAllGroups = lambda: pytest.fail("Known message context must skip lookup")
    api._pins().list = lambda thread_id, thread_type: api._pins()._resolve_thread(thread_id, thread_type)
    seen = []
    api.onMessage = lambda *args: seen.append(api.getPinnedMessages(args[-2]))
    api._handle_incoming_message("m1", "42", "hello", message(), "987", ThreadType.GROUP)
    assert seen == [("987", ThreadType.GROUP)]


def test_pin_event_context_is_known_before_callback():
    api, _ = api_with_friend({"data": [], "version": 0})
    api.fetchAllGroups = lambda: pytest.fail("Known event context must skip lookup")
    seen = []
    api._pins().list = lambda thread_id, thread_type: api._pins()._resolve_thread(thread_id, thread_type)
    api.onPinEvent = lambda event: seen.append(api.getPinnedMessages(event.thread_id))
    api.onErrorCallBack = lambda error: (_ for _ in ()).throw(error)
    api._handle_ws_controls([{"content": {"act_type": "group", "act": "pin_create",
        "data": {"groupId": "987", "actorId": "42", "topic": topic()}}}])
    assert seen == [("987", ThreadType.GROUP)]


@pytest.mark.parametrize("groups", [{}, {"gridVerMap": []}, {"error_code": 1, "gridVerMap": {}}])
def test_invalid_detection_does_not_call_pin_transport(groups):
    api, calls = api_with_friend({"data": [], "version": 0})
    api.fetchAllGroups = lambda: groups
    with pytest.raises(ZaloAPIException, match="Cannot detect"):
        api.pinMessage(message(), "987")
    assert calls == []


def test_detection_request_failure_is_propagated_without_pinning():
    api, calls = api_with_friend({"data": [], "version": 0})
    def fail():
        raise ZaloAPIException("lookup failed")
    api.fetchAllGroups = fail
    with pytest.raises(ZaloAPIException, match="lookup failed"):
        api.pinMessage(message(), "987")
    assert calls == []


def test_explicit_type_skips_detection_and_cloud_id_is_rejected():
    api, calls = api_with_friend({"data": [], "version": 0})
    api.fetchAllGroups = lambda: pytest.fail("Explicit type must skip lookup")
    assert api.getPinnedMessages("123", ThreadType.USER) == []
    api.cloud_id = "cloud-id"
    with pytest.raises(ZaloUserError, match="CLOUD"):
        api.getPinnedMessages("cloud-id")
    assert len(calls) == 1
