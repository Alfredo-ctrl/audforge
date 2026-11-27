# audforge

Trim, normalize and convert audio from the terminal. It wraps ffmpeg's audio filters in small named ops, so a podcast edit is a list — trim, normalize, fade_out — instead of a filter string you have to look up.

It shells out to ffmpeg, so install that first (`apt install ffmpeg` / `brew install ffmpeg`).

## Install

```sh
pip install audforge
```

## Use it from the terminal

```sh
# what can it do?
audforge ops

# describe a file
audforge describe -i voice.mp3

# edit it: keep seconds 2-10, normalize to podcast loudness, fade out
audforge edit -i voice.mp3 -o voice-edit.mp3 --ops '[
  {"op": "trim", "start": 2, "end": 10},
  {"op": "normalize", "target_lufs": -16},
  {"op": "fade_out", "duration": 1}
]'
```

Output is JSON, so it is easy to parse:

```json
{"output": "voice-edit.mp3", "duration": 8.0, "sample_rate": 44100, "channels": 2, "codec": "mp3", "ops_applied": ["trim", "normalize", "fade_out"]}
```

More one-liners:

```sh
# trim the silence off a voice note
audforge edit -i note.m4a -o note-clean.m4a --ops '[{"op": "silence_trim"}]'

# convert to wav at 16kHz, ready for a speech model
audforge edit -i song.mp3 -o song-16k.wav --ops '[{"op": "convert", "format": "wav"}, {"op": "resample", "rate": 16000}]'

# stick takes together
audforge join -i take1.mp3 take2.mp3 -o full.mp3

# transcribe with local Whisper (needs the whisper CLI)
audforge transcribe -i interview.mp3 --model tiny --language es
```

## How an agent uses it

You turn the user's words into ops. `audforge ops` lists every operation with its parameters and valid ranges, so there is nothing to guess. The usual requests:

- "cut the first 5 seconds and make it mono" -> trim, mono
- "this podcast is too quiet and uneven" -> normalize
- "turn this into a 16kHz wav for my model" -> convert, resample

Missing an op? CONTRIBUTING.md explains how to add one — same shape as the rest, with a test on the fixture audio.

## Use it from Python

```python
from audforge import apply_ops, transcribe

out = apply_ops("voice.mp3", "voice-edit.mp3", [
    {"op": "trim", "start": 2, "end": 10},
    {"op": "normalize"},
])

print(transcribe("interview.mp3", model="tiny", language="es")["text"])
```

## MCP server

Any MCP client can use audforge as tools, including transcribe_audio:

```sh
audforge mcp
```

It speaks MCP over stdio and exposes `edit_audio`, `describe_audio`, `list_operations`, `join_audios` and `transcribe_audio`. Example client config:

```json
{
  "mcpServers": {
    "audforge": {"command": "audforge", "args": ["mcp"]}
  }
}
```

## License

MIT
