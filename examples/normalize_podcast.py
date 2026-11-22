"""Podcast cleanup: trim the dead air, even out the loudness, fade the edges."""

from audforge import apply_ops

out = apply_ops("episode-raw.mp3", "episode.mp3", [
    {"op": "silence_trim"},
    {"op": "normalize", "target_lufs": -16},
    {"op": "fade_in", "duration": 0.5},
    {"op": "fade_out", "duration": 1},
])
print(out)
