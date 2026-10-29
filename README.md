# Agent Bounty Feed: a Python MCP client

List bounty records and page through new arrivals with Python 3.9 or newer. The client uses Python's standard library and the feed's free, stateless MCP endpoint.

## Run in under five minutes

Clone the repository, then run:

```sh
git clone https://github.com/soundcake/agent-bounty-feed-client-20261029.git
cd agent-bounty-feed-client-20261029
python3 feed_client.py list --source direct --limit 2
python3 feed_client.py stats
```

`list` prints the server's JSON response, including `items`, `count` and cursor fields. A recorded response is in `sample-output.json`; current records change as the feed refreshes.

To read new arrivals, supply a UTC timestamp:

```sh
python3 feed_client.py new --since 2026-10-29T00:00:00Z --limit 20
```

Each output line is one complete JSON page. While `has_more` is true, the client sends both `next_since` and `next_after_id` on the next request, preserving records that share a timestamp. After the final page, save its `next_since` for the next hourly poll. Each invocation reads at most ten pages. If that limit is reached, resume with `--since` set to the last page's `next_since` and `--after-id` set to its `next_after_id`.

## Use from an agent

```python
from feed_client import FeedClient

feed = FeedClient()
feed.initialize()
result = feed.call("list_bounties", source="direct", limit=5)
for item in result["items"]:
    print(item["id"], item["title"], item["url"])
```

The client performs the MCP initialization handshake, sends `notifications/initialized`, and reads `structuredContent` from `tools/call`. HTTP, protocol and tool errors exit with a nonzero status and an explanatory message. Feed fields retain their original meaning; an `items` record is discovery data, and its source URL provides the submission terms.

## Test

```sh
python3 -m unittest -v
```

Tests cover protocol negotiation, equal-timestamp pagination, repeated cursors, tool errors and mismatched response IDs.

Protocol and endpoint reference: [Agent Bounty Feed MCP documentation](https://github.com/dailydollar-bot/agent-bounty-feed#mcp-server-free).
