"""A fake `hal acp` that raises one broker permission request per prompt.

The prompt text is used as the tool call's title (`name [tier] pack`), and the client's
answer is appended to the log file named by the first argument.
"""

import json
import sys

log = open(sys.argv[1], "a", encoding="utf-8")


def send(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


for line in sys.stdin:
    msg = json.loads(line)
    method, rid = msg.get("method"), msg.get("id")
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": rid, "result": {"protocolVersion": 1}})
    elif method == "session/new":
        send({"jsonrpc": "2.0", "id": rid, "result": {"sessionId": "s1"}})
    elif method == "session/prompt":
        title = msg["params"]["prompt"][-1]["text"]
        send(
            {
                "jsonrpc": "2.0",
                "id": 900,
                "method": "session/request_permission",
                "params": {
                    "sessionId": "s1",
                    "toolCall": {"toolCallId": "t1", "title": title},
                    "options": [{"optionId": "allow-1", "name": "Allow", "kind": "allow_once"}],
                    "_meta": {"hal/origin": "broker", "hal/summary": f"Allow {title}?"},
                },
            }
        )
        answer = json.loads(sys.stdin.readline())
        log.write(json.dumps(answer["result"]) + "\n")
        log.flush()
        send(
            {
                "jsonrpc": "2.0",
                "method": "session/update",
                "params": {
                    "sessionId": "s1",
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"type": "text", "text": "Done."},
                    },
                },
            }
        )
        send({"jsonrpc": "2.0", "id": rid, "result": {"stopReason": "end_turn"}})
