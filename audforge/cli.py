"""audforge command line. Built for agents: JSON in, JSON out."""

import argparse
import json
import sys

from . import __version__, apply_ops, describe, join_audios, list_ops, transcribe


def _fail(msg):
    print(json.dumps({"error": msg}), file=sys.stderr)
    raise SystemExit(1)


def _ok(payload):
    print(json.dumps(payload))


def cmd_edit(args):
    try:
        ops = json.loads(args.ops)
        result = apply_ops(args.input, args.output, ops)
    except (ValueError, RuntimeError, json.JSONDecodeError) as e:
        _fail(str(e))
    _ok(result)


def cmd_ops(args):
    _ok(list_ops())


def cmd_describe(args):
    try:
        result = describe(args.input)
    except ValueError as e:
        _fail(str(e))
    _ok(result)


def cmd_join(args):
    try:
        result = join_audios(args.inputs, args.output)
    except (ValueError, RuntimeError) as e:
        _fail(str(e))
    _ok(result)


def cmd_transcribe(args):
    try:
        result = transcribe(args.input, model=args.model, language=args.language)
    except (ValueError, RuntimeError) as e:
        _fail(str(e))
    _ok(result)


def cmd_mcp(args):
    from .mcp_server import run

    run()


def main(argv=None):
    parser = argparse.ArgumentParser(prog="audforge", description="Audio editing for AI agents.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_edit = sub.add_parser("edit", help="Apply operations to an audio file and save the result.")
    p_edit.add_argument("-i", "--input", required=True, help="Input audio path")
    p_edit.add_argument("-o", "--output", required=True, help="Output audio path")
    p_edit.add_argument("--ops", required=True, help='JSON list of ops, e.g. \'[{"op": "trim", "start": 2, "end": 8}]\'')
    p_edit.set_defaults(func=cmd_edit)

    p_ops = sub.add_parser("ops", help="List every operation with its parameters.")
    p_ops.set_defaults(func=cmd_ops)

    p_desc = sub.add_parser("describe", help="Print audio info as JSON.")
    p_desc.add_argument("-i", "--input", required=True, help="Input audio path")
    p_desc.set_defaults(func=cmd_describe)

    p_join = sub.add_parser("join", help="Join two or more audio files into one.")
    p_join.add_argument("-i", "--inputs", nargs="+", required=True, help="Input audio files in order")
    p_join.add_argument("-o", "--output", required=True, help="Output audio path")
    p_join.set_defaults(func=cmd_join)

    p_tr = sub.add_parser("transcribe", help="Transcribe audio to text with local Whisper.")
    p_tr.add_argument("-i", "--input", required=True, help="Input audio path")
    p_tr.add_argument("--model", default="tiny", help="Whisper model: tiny, base, small, medium, large (default: tiny)")
    p_tr.add_argument("--language", default=None, help="Language code, e.g. es, en. Auto-detects if omitted.")
    p_tr.set_defaults(func=cmd_transcribe)

    p_mcp = sub.add_parser("mcp", help="Start the MCP server on stdio.")
    p_mcp.set_defaults(func=cmd_mcp)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
