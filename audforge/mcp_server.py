"""Minimal MCP server over stdio. No dependencies, plain JSON-RPC.

Tools: edit_audio, describe_audio, list_operations, join_audios, transcribe_audio.
"""

import json
import sys

from . import __version__, apply_ops, describe, join_audios, list_ops, transcribe

TOOLS = [
    {
        "name": "edit_audio",
        "description": "Apply a list of audio operations and save the result. Ops are the same ones list_operations returns.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Input audio path"},
                "output": {"type": "string", "description": "Output audio path"},
                "ops": {"type": "array", "items": {"type": "object"}, "description": "Ops to apply, e.g. [{\"op\": \"trim\", \"start\": 2, \"end\": 8}]"},
            },
            "required": ["input", "output", "ops"],
        },
    },
    {
        "name": "describe_audio",
        "description": "Get duration, sample rate, channels and codec of an audio file.",
        "inputSchema": {
            "type": "object",
            "properties": {"input": {"type": "string", "description": "Audio path"}},
            "required": ["input"],
        },
    },
    {
        "name": "list_operations",
        "description": "List every operation with its parameters and valid ranges.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "join_audios",
        "description": "Join two or more audio files into one, in order.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "inputs": {"type": "array", "items": {"type": "string"}, "description": "Input audio files in order"},
                "output": {"type": "string", "description": "Output audio path"},
            },
            "required": ["inputs", "output"],
        },
    },
    {
        "name": "transcribe_audio",
        "description": "Transcribe audio to text with local Whisper. Needs the whisper CLI installed.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Audio path"},
                "model": {"type": "string", "description": "Whisper model: tiny, base, small, medium, large", "default": "tiny"},
                "language": {"type": "string", "description": "Language code, e.g. es, en. Auto-detects if omitted."},
            },
            "required": ["input"],
        },
    },
]


def _text(payload):
    return {"content": [{"type": "text", "text": json.dumps(payload)}]}


def _call(name, args):
    if name == "list_operations":
        return _text(list_ops())
    if name == "describe_audio":
        return _text(describe(args["input"]))
    if name == "edit_audio":
        return _text(apply_ops(args["input"], args["output"], args["ops"]))
    if name == "join_audios":
        return _text(join_audios(args["inputs"], args["output"]))
    if name == "transcribe_audio":
        return _text(transcribe(args["input"], model=args.get("model", "tiny"), language=args.get("language")))
    raise ValueError(f"unknown tool '{name}'")


def run():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = req.get("method", "")
        req_id = req.get("id")
        if method in ("notifications/initialized", "notifications/cancelled"):
            continue
        if method == "initialize":
            result = {
                "protocolVersion": req.get("params", {}).get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "audforge", "version": __version__},
            }
            resp = {"result": result}
        elif method == "ping":
            resp = {"result": {}}
        elif method == "tools/list":
            resp = {"result": {"tools": TOOLS}}
        elif method == "tools/call":
            try:
                resp = {"result": _call(req["params"]["name"], req["params"].get("arguments", {}))}
            except Exception as e:
                resp = {"result": {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}}
        else:
            resp = {"error": {"code": -32601, "message": f"method not found: {method}"}}
        if req_id is not None:
            print(json.dumps({"jsonrpc": "2.0", "id": req_id, **resp}), flush=True)
