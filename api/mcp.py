import json
import random
from http.server import BaseHTTPRequestHandler

SERVER_INFO = {"name": "snake-dice-mcp", "version": "1.0.0"}
SUPPORTED_VERSIONS = ["2025-06-18", "2025-03-26", "2024-11-05"]

TOOLS = [
    {
        "name": "roll_dice",
        "description": (
            "Roll one or more dice for the player and return each roll and the total. "
            "Use this when the player wants to roll or asks for a random dice result."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "description": "How many dice (1-10)", "default": 1},
                "sides": {"type": "integer", "description": "Sides per die (2-100)", "default": 6},
            },
        },
    },
    {
        "name": "dice_odds",
        "description": (
            "Exact probability of getting a given total when rolling dice. "
            "Use this for questions about odds, chances or probability."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "total": {"type": "integer", "description": "The total you want"},
                "dice": {"type": "integer", "description": "How many dice (1-10)", "default": 1},
                "sides": {"type": "integer", "description": "Sides per die (2-100)", "default": 6},
            },
            "required": ["total"],
        },
    },
]


def _check(dice, sides):
    if not 1 <= dice <= 10:
        raise ValueError("number of dice must be between 1 and 10")
    if not 2 <= sides <= 100:
        raise ValueError("sides must be between 2 and 100")


def roll_dice(args):
    count = int(args.get("count", 1))
    sides = int(args.get("sides", 6))
    _check(count, sides)
    rolls = [random.randint(1, sides) for _ in range(count)]
    return {"rolls": rolls, "total": sum(rolls), "sides": sides}


def dice_odds(args):
    total = int(args["total"])
    dice = int(args.get("dice", 1))
    sides = int(args.get("sides", 6))
    _check(dice, sides)
    ways = {0: 1}  # ways[s] = number of ways to reach sum s
    for _ in range(dice):
        nxt = {}
        for s, c in ways.items():
            for face in range(1, sides + 1):
                nxt[s + face] = nxt.get(s + face, 0) + c
        ways = nxt
    outcomes = sides ** dice
    hit = ways.get(total, 0)
    return {
        "total": total,
        "dice": dice,
        "sides": sides,
        "ways": hit,
        "outcomes": outcomes,
        "probability": hit / outcomes,
        "percent": f"{100 * hit / outcomes:.2f}%",
    }


IMPLS = {"roll_dice": roll_dice, "dice_odds": dice_odds}


def _ok(mid, result):
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _err(mid, code, message):
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def handle_rpc(msg):
    """Return a JSON-RPC response dict, or None when no response is needed."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        return _err(None, -32600, "Invalid Request")
    method = msg.get("method")
    mid = msg.get("id")
    params = msg.get("params") or {}
    if method is None:          # a response from the client, nothing to do
        return None
    if "id" not in msg:         # a notification, never answered
        return None

    if method == "initialize":
        asked = params.get("protocolVersion")
        version = asked if asked in SUPPORTED_VERSIONS else SUPPORTED_VERSIONS[0]
        return _ok(mid, {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
        })
    if method == "ping":
        return _ok(mid, {})
    if method == "tools/list":
        return _ok(mid, {"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name")
        impl = IMPLS.get(name)
        if impl is None:
            return _err(mid, -32602, f"Unknown tool: {name}")
        try:
            out = impl(params.get("arguments") or {})
            return _ok(mid, {"content": [{"type": "text", "text": json.dumps(out)}], "isError": False})
        except Exception as e:
            return _ok(mid, {"content": [{"type": "text", "text": f"Tool error: {e}"}], "isError": True})
    return _err(mid, -32601, f"Method not found: {method}")


class handler(BaseHTTPRequestHandler):
    def _send(self, status, payload=None):
        body = b"" if payload is None else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        if body:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length) or b"null")
        except Exception:
            return self._send(400, _err(None, -32700, "Parse error"))
        if isinstance(data, list):
            replies = [r for r in (handle_rpc(m) for m in data) if r is not None]
            return self._send(200, replies) if replies else self._send(202)
        reply = handle_rpc(data)
        return self._send(200, reply) if reply is not None else self._send(202)

    def _no_stream(self):
        self.send_response(405)
        self.send_header("Allow", "POST")
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_GET = _no_stream
    do_DELETE = _no_stream
