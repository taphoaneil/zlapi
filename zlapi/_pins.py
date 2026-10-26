"""The public, thread-independent pinned-message API."""
from dataclasses import dataclass, field
from typing import Any, List, Optional

from ._aevents import PinEventType
from ._exception import ZaloAPIException, ZaloUserError
from ._threads import ThreadType
from . import _util


@dataclass
class PinnedMessage:
    id: str
    thread_id: str
    thread_type: ThreadType
    message_id: Optional[str] = None
    client_message_id: Optional[str] = None
    params: Any = None
    raw: Any = None
    _token: Any = None


@dataclass
class UnpinFailure:
    id: str
    message: str
    status: str = "attempted"
    code: Any = None


@dataclass
class UnpinResult:
    requested_ids: List[str] = field(default_factory=list)
    removed_ids: List[str] = field(default_factory=list)
    already_absent_ids: List[str] = field(default_factory=list)
    failures: List[UnpinFailure] = field(default_factory=list)


@dataclass
class PinEvent:
    type: PinEventType
    thread_id: str
    thread_type: ThreadType
    actor_id: Optional[str]
    pin_ids: List[str] = field(default_factory=list)
    pins: List[PinnedMessage] = field(default_factory=list)
    raw: Any = None


class PinService:
    """Adapts Zalo's separate friendboard and groupboard wire protocols."""
    def __init__(self, client):
        self.client = client
        self._thread_types = {}

    def remember_thread(self, thread_id, thread_type):
        """Keep authoritative context from messages, events and explicit calls."""
        if thread_id is not None and thread_type in (ThreadType.USER, ThreadType.GROUP, ThreadType.CLOUD):
            self._thread_types[str(thread_id)] = thread_type

    def _resolve_thread(self, thread_id, thread_type):
        thread_id = self.client._pin_id(thread_id, "thread_id")
        cloud_id = getattr(self.client, "cloud_id", None)
        if cloud_id and thread_id == str(cloud_id):
            thread_type = ThreadType.CLOUD
        if thread_type is None:
            thread_type = self._thread_types.get(thread_id)
        if thread_type is None:
            groups = self.client.fetchAllGroups()
            if hasattr(groups, "toDict"):
                groups = groups.toDict()
            group_ids = groups.get("gridVerMap") if isinstance(groups, dict) else None
            if not isinstance(group_ids, dict) or groups.get("error_code", 0) != 0:
                raise ZaloAPIException("Cannot detect pin thread type: invalid group list; pass thread_type explicitly")
            thread_type = ThreadType.GROUP if thread_id in {str(key) for key in group_ids} else ThreadType.USER
        self._thread(thread_id, thread_type)
        self.remember_thread(thread_id, thread_type)
        return thread_id, thread_type

    def _thread(self, thread_id, thread_type):
        if thread_type == ThreadType.CLOUD:
            raise ZaloUserError("Pinned messages are not supported for ThreadType.CLOUD")
        if thread_type not in (ThreadType.USER, ThreadType.GROUP):
            raise ZaloUserError("Pinned messages require ThreadType.USER or ThreadType.GROUP")
        return self.client._pin_id(thread_id, "thread_id")

    def _pin(self, topic, thread_id, thread_type, token=None):
        topic = self.client._normalize_pin_topic(topic)
        params = topic.get("params")
        if hasattr(params, "toDict"):
            params = params.toDict()
        if not isinstance(params, dict):
            params = {}
        return PinnedMessage(str(topic.get("id") or topic.get("topicId")), thread_id, thread_type,
            str(params["global_msg_id"]) if params.get("global_msg_id") is not None else None,
            str(params["client_msg_id"]) if params.get("client_msg_id") is not None else None,
            params, topic, token)

    def list(self, thread_id, thread_type):
        thread_id, thread_type = self._resolve_thread(thread_id, thread_type)
        if thread_type == ThreadType.USER:
            result = self.client._friend_board_request("list", {"conversationId": thread_id, "version": 0})
            try:
                topics = self.client._pin_json(result["data"])
                version = result["version"]
            except (KeyError, TypeError, ValueError) as error:
                raise ZaloAPIException("Invalid friend pin list: %s" % error) from error
            if not isinstance(topics, list):
                raise ZaloAPIException("Invalid friend pin list: expected a list")
            return [self._pin(t, thread_id, thread_type, version) for t in topics
                    if str(self.client._normalize_pin_topic(t).get("type")) == "2"]
        response = self.client._get("https://groupboard-wpa.chat.zalo.me/api/board/pin/list", params={
            "zpw_ver": _util.ZPW_VER, "zpw_type": _util.ZPW_TYPE,
            "params": self.client._encode({"groupId": thread_id, "boardVersion": 0, "imei": self.client._imei}),
        })
        try:
            outer = response.json()
            if outer.get("error_code") != 0:
                raise ZaloAPIException("Error #%s: %s" % (outer.get("error_code"), outer.get("error_message")))
            payload = self.client._decode(outer["data"])
            if payload.get("error_code", 0) != 0:
                raise ZaloAPIException("Error #%s: %s" % (payload.get("error_code"), payload.get("error_message")))
            board = payload["data"]
            topics, version = board["items"], board["boardVersion"]
        except (KeyError, TypeError, ValueError) as error:
            raise ZaloAPIException("Invalid group pin list: %s" % error) from error
        if not isinstance(topics, list):
            raise ZaloAPIException("Invalid group pin list: expected a list")
        return [self._pin(topic, thread_id, thread_type, version) for topic in topics
                if str(self.client._normalize_pin_topic(topic).get("type")) == "2"]

    def create(self, message, thread_id, thread_type):
        thread_id, thread_type = self._resolve_thread(thread_id, thread_type)
        self.client._pin_id(getattr(message, "msgId", None), "message.msgId")
        self.client._pin_id(getattr(message, "cliMsgId", None), "message.cliMsgId")
        encoded = self.client._pin_message_params(message)
        if encoded is None:
            raise ZaloUserError("Unsupported pin message type: %s" % getattr(message, "msgType", None))
        if thread_type == ThreadType.USER:
            result = self.client._friend_board_request("create", {"conversationId": thread_id, "version": 0, "lang": "vi",
                "topic": {"type": 2, "color": -14540254, "emoji": "📌", "duration": 0, "imei": self.client._imei,
                          "pinAct": 1, "src": -1, "params": encoded}})
            topic = result.get("data")
            if topic is None:
                raise ZaloAPIException("Invalid created friend pin")
            return self._pin(topic, thread_id, thread_type, result.get("version"))
        response = self.client._post("https://groupboard-wpa.chat.zalo.me/api/board/topic/createv2",
            params={"zpw_ver": _util.ZPW_VER, "zpw_type": _util.ZPW_TYPE},
            data={"params": self.client._encode({"grid": thread_id, "type": 2, "color": -14540254, "emoji": "📌",
                "duration": 0, "imei": self.client._imei, "pinAct": 1, "params": encoded})})
        outer = response.json()
        if outer.get("error_code") != 0:
            raise ZaloAPIException("Error #%s: %s" % (outer.get("error_code"), outer.get("error_message") or outer.get("data")))
        # createv2 returns a board-operation ID, not reliably the topic ID used
        # by unpinv2. Resolve the actual board record before exposing it.
        wanted_message_id = str(getattr(message, "msgId"))
        wanted_client_id = str(getattr(message, "cliMsgId"))
        for pin in self.list(thread_id, thread_type):
            if pin.message_id == wanted_message_id and pin.client_message_id == wanted_client_id:
                return pin
        raise ZaloAPIException("Created group pin was not found on the group board")

    def remove(self, pin_id, thread_id, thread_type):
        thread_id, thread_type = self._resolve_thread(thread_id, thread_type); pin_id = self.client._pin_id(pin_id, "pin_id")
        result = UnpinResult(requested_ids=[pin_id])
        pins = self.list(thread_id, thread_type)
        pin = next((p for p in pins if p.id == pin_id), None)
        if pin is None:
            result.already_absent_ids.append(pin_id); return result
        try:
            if thread_type == ThreadType.USER:
                self.client._friend_board_request("multi_unpin", {"conversationId": thread_id,
                    "topics": [{"topicId": pin_id, "topicType": 2}], "version": pin._token, "lang": "vi"})
            else:
                response = self.client._get("https://groupboard-wpa.chat.zalo.me/api/board/unpinv2", params={"zpw_ver": _util.ZPW_VER,
                    "zpw_type": _util.ZPW_TYPE, "params": self.client._encode({"grid": thread_id, "imei": self.client._imei,
                    "topic": {"topicId": pin_id, "topicType": 2}, "boardVersion": int(pin._token)})})
                outer = response.json()
                if outer.get("error_code") != 0: raise ZaloAPIException(str(outer.get("error_message") or outer.get("data")))
                payload = self.client._decode(outer.get("data"))
                if isinstance(payload, dict) and payload.get("error_code", 0) != 0:
                    raise ZaloAPIException("Error #%s: %s" % (payload.get("error_code"), payload.get("error_message")))
                # groupboard can acknowledge a stale request in its outer
                # envelope. Confirm the board itself before reporting success.
                if any(current.id == pin_id for current in self.list(thread_id, thread_type)):
                    raise ZaloAPIException("Group pin was not removed by the server")
            result.removed_ids.append(pin_id)
        except Exception as error:
            result.failures.append(UnpinFailure(pin_id, str(error)))
        return result

    def remove_all(self, thread_id, thread_type):
        thread_id, thread_type = self._resolve_thread(thread_id, thread_type)
        pins = self.list(thread_id, thread_type)
        result = UnpinResult(requested_ids=[p.id for p in pins])
        for pin in pins:
            one = self.remove(pin.id, thread_id, thread_type)
            result.removed_ids.extend(one.removed_ids); result.already_absent_ids.extend(one.already_absent_ids); result.failures.extend(one.failures)
        return result
