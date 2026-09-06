import unittest
from types import SimpleNamespace
from unittest.mock import patch

from zlapi import ZaloAPI
from zlapi._client import _normalize_cloud_thread
from zlapi._state import State
from zlapi.models import ThreadType, ZaloUserError


class CloudThreadTests(unittest.TestCase):
    def test_cloud_is_a_distinct_thread_type(self):
        self.assertNotEqual(ThreadType.CLOUD, ThreadType.USER)
        self.assertNotEqual(ThreadType.CLOUD, ThreadType.GROUP)

    def test_cloud_route_uses_verified_id_and_direct_message_type(self):
        class Probe:
            cloud_id = "cloud-123"

            def _require_cloud_id(self):
                return self.cloud_id

            @_normalize_cloud_thread
            def send(self, message, thread_id, thread_type):
                return thread_id, thread_type

        self.assertEqual(
            Probe().send("test", thread_type=ThreadType.CLOUD),
            ("cloud-123", ThreadType.USER),
        )

    def test_cloud_route_rejects_missing_verified_id(self):
        api = ZaloAPI(auto_login=False)
        with self.assertRaises(ZaloUserError):
            api._require_cloud_id()

    def test_constructor_loads_cookies_without_auto_login(self):
        api = ZaloAPI(cookies={"session": "test"}, auto_login=False)
        self.assertEqual(api.getSession(), {"session": "test"})

    def test_listener_classifies_cloud_by_canonical_thread_id(self):
        api = ZaloAPI(auto_login=False)
        api.cloud_id = "cloud-123"
        thread_id, thread_type = api._direct_thread_context(
            SimpleNamespace(uidFrom="0", idTo="cloud-123")
        )
        self.assertEqual(thread_id, "cloud-123")
        self.assertEqual(thread_type, ThreadType.CLOUD)

    def test_login_uses_server_send2me_id_not_account_uid(self):
        response = SimpleNamespace(
            json=lambda: {
                "data": {
                    "uid": "account-1",
                    "send2me_id": "cloud-9",
                    "phone_number": "",
                    "zpw_enk": "secret",
                    "zpw_ws": "websocket",
                }
            }
        )
        state = State()
        state.set_cookies({"session": "test"})
        with patch("zlapi._state.requests.get", return_value=response):
            state.login(None, None, "test-imei")

        self.assertEqual(state.account_id, "account-1")
        self.assertEqual(state.cloud_id, "cloud-9")
        self.assertEqual(state.user_id, "account-1")


if __name__ == "__main__":
    unittest.main()
