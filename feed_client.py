"""A small client for Agent Bounty Feed's stateless JSON MCP endpoint."""
import argparse
import json
import sys
import urllib.error
import urllib.request

ENDPOINT = "https://agent-bounty-feed.dailydollar.workers.dev/mcp"


class FeedError(Exception):
    pass


class FeedClient:
    def __init__(self, endpoint=ENDPOINT, opener=urllib.request.urlopen):
        self.endpoint, self.opener = endpoint, opener
        self.sequence = 0
        self.protocol = "2025-03-26"

    def rpc(self, method, params=None, notification=False):
        message = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if not notification:
            self.sequence += 1
            message["id"] = self.sequence
        request = urllib.request.Request(
            self.endpoint, data=json.dumps(message).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "feed-cursor-demo/0.1.0",
                     "Accept": "application/json, text/event-stream",
                     "MCP-Protocol-Version": self.protocol}, method="POST")
        try:
            with self.opener(request, timeout=20) as response:
                raw = response.read(4 * 1024 * 1024 + 1)
        except urllib.error.HTTPError as exc:
            raise FeedError(f"HTTP {exc.code}; retry later if the server is unavailable") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise FeedError(f"Connection failed: {exc}") from exc
        if notification:
            return None
        if len(raw) > 4 * 1024 * 1024:
            raise FeedError("Response exceeds 4 MiB")
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise FeedError("Expected a JSON response from the feed endpoint") from exc
        if not isinstance(data, dict) or data.get("jsonrpc") != "2.0" or data.get("id") != message["id"]:
            raise FeedError("Invalid or mismatched JSON-RPC response")
        if "error" in data:
            raise FeedError(f"JSON-RPC error: {data['error']}")
        if not isinstance(data.get("result"), dict):
            raise FeedError("Missing JSON-RPC result")
        return data["result"]

    def initialize(self):
        result = self.rpc("initialize", {"protocolVersion": self.protocol,
            "capabilities": {}, "clientInfo": {"name": "feed-cursor-demo", "version": "0.1.0"}})
        if result.get("protocolVersion") not in ("2024-11-05", "2025-03-26", "2025-06-18"):
            raise FeedError("Unsupported negotiated protocol version")
        self.protocol = result["protocolVersion"]
        self.rpc("notifications/initialized", notification=True)

    def call(self, name, **arguments):
        result = self.rpc("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            raise FeedError(f"Tool failed: {result.get('content')}")
        data = result.get("structuredContent")
        if not isinstance(data, dict):
            raise FeedError("Missing feed structuredContent")
        return data

    def new_pages(self, since, limit=100, max_pages=10, after_id=None):
        cursor = (since, after_id)
        seen = set()
        for _ in range(max_pages):
            if cursor in seen:
                raise FeedError("Server repeated its pagination cursor")
            seen.add(cursor)
            args = {"since": cursor[0], "limit": limit}
            if cursor[1] is not None:
                args["after_id"] = cursor[1]
            page = self.call("get_new_bounties", **args)
            yield page
            if not page.get("has_more"):
                return
            cursor = (page.get("next_since"), page.get("next_after_id"))
            if not all(isinstance(v, str) and v for v in cursor):
                raise FeedError("Missing pagination cursor")
        raise FeedError("Page limit reached; resume using the last page's cursor")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["list", "stats", "new"], nargs="?", default="list")
    parser.add_argument("--source", help="Optional feed source, such as direct")
    parser.add_argument("--limit", type=int, choices=range(1, 101), default=5, metavar="1..100")
    parser.add_argument("--since", help="UTC timestamp required by new")
    parser.add_argument("--after-id", help="Resume new with the last page's next_after_id")
    args = parser.parse_args()
    if args.command == "new" and not args.since:
        parser.error("new requires --since")
    client = FeedClient()
    try:
        client.initialize()
        if args.command == "new":
            for page in client.new_pages(args.since, args.limit, after_id=args.after_id):
                print(json.dumps(page))
        else:
            options = {"limit": args.limit} if args.command == "list" else {}
            if args.source and args.command == "list":
                options["source"] = args.source
            data = client.call("list_bounties" if args.command == "list" else "get_feed_stats", **options)
            print(json.dumps(data, indent=2))
    except FeedError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
