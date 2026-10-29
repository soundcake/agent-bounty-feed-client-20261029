import io
import json
import unittest
from unittest.mock import Mock
from feed_client import FeedClient, FeedError


class FeedClientTests(unittest.TestCase):
    def test_handshake_and_structured_tool_output(self):
        requests = []
        def server(request, timeout):
            body = json.loads(request.data)
            requests.append((body, dict(request.header_items())))
            if "id" not in body:
                return io.BytesIO(b"")
            result = ({"protocolVersion": "2025-06-18"} if body["method"] == "initialize"
                      else {"structuredContent": {"items": [{"id": "fixture"}]}})
            return io.BytesIO(json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": result}).encode())
        client = FeedClient(opener=server)
        client.initialize()
        self.assertEqual(client.call("list_bounties", limit=1)["items"][0]["id"], "fixture")
        self.assertEqual(requests[1][0]["method"], "notifications/initialized")
        self.assertNotIn("id", requests[1][0])
        self.assertEqual(requests[2][1]["Mcp-protocol-version"], "2025-06-18")

    def test_same_timestamp_pages_use_id_tiebreaker(self):
        client = FeedClient()
        client.call = Mock(side_effect=[
            {"items": [{"id": "a"}], "has_more": True, "next_since": "2026-10-29T12:00:00Z", "next_after_id": "a"},
            {"items": [{"id": "b"}], "has_more": False}])
        pages = list(client.new_pages("2026-10-29T11:00:00Z", limit=1))
        self.assertEqual([i["id"] for p in pages for i in p["items"]], ["a", "b"])
        client.call.assert_called_with("get_new_bounties", since="2026-10-29T12:00:00Z", after_id="a", limit=1)

    def test_repeated_cursor_stops(self):
        client = FeedClient()
        client.call = Mock(return_value={"has_more": True, "next_since": "time", "next_after_id": "a"})
        with self.assertRaisesRegex(FeedError, "repeated"):
            list(client.new_pages("start"))
        self.assertEqual(client.call.call_count, 2)

    def test_resume_preserves_both_cursor_parts(self):
        client = FeedClient()
        client.call = Mock(return_value={"has_more": False, "items": []})
        list(client.new_pages("2026-10-29T12:00:00Z", after_id="already-seen"))
        client.call.assert_called_once_with("get_new_bounties", since="2026-10-29T12:00:00Z", after_id="already-seen", limit=100)

    def test_tool_errors_are_not_empty_success(self):
        client = FeedClient()
        client.rpc = Mock(return_value={"isError": True, "content": [{"type": "text", "text": "feed unavailable"}]})
        with self.assertRaisesRegex(FeedError, "feed unavailable"):
            client.call("list_bounties")

    def test_wrong_response_id_rejected(self):
        client = FeedClient(opener=lambda *a, **k: io.BytesIO(b'{"jsonrpc":"2.0","id":999,"result":{}}'))
        with self.assertRaisesRegex(FeedError, "mismatched"):
            client.rpc("ping")


if __name__ == "__main__":
    unittest.main()
