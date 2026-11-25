"""Audio ops. One op = one entry in OPS plus one small builder below.

Every op turns into ffmpeg audio filters, so the whole edit runs in one
ffmpeg call. No GUI, no account, just ffmpeg doing the work.
"""

import json
import subprocess

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"

# output extension -> encoder, used when no op picks a format
CODECS = {
    "mp3": "libmp3lame",
    "wav": "pcm_s16le",
    "aac": "aac",
    "ogg": "libvorbis",
    "flac": "flac",
    "m4a": "aac",
}


class Ctx:
    """Everything builders collect while walking the ops list."""

    def __init__(self):
        self.af = []
        self.start = None
        self.duration = None
        self.audio_format = None  # set by convert: mp3, wav, aac, ogg, flac, m4a


def _num(op, params, key, default=None, lo=None, hi=None):
    v = params.get(key, default)
    if v is None:
        raise ValueError(f"'{op}' needs '{key}'")
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"'{op}': '{key}' has to be a number, got {params.get(key)!r}")
    if lo is not None and v < lo:
        raise ValueError(f"'{op}': '{key}' can't be under {lo}")
    if hi is not None and v > hi:
        raise ValueError(f"'{op}': '{key}' can't be over {hi}")
    return v


def _int(op, params, key, default=None, lo=None, hi=None):
    v = _num(op, params, key, default, lo, hi)
    if v != int(v):
        raise ValueError(f"'{op}': '{key}' has to be a whole number")
    return int(v)


def _atempo_chain(factor):
    # atempo only takes 0.5-2.0, so chain it for bigger changes
    parts = []
    f = factor
    while f > 2.0:
        parts.append("atempo=2.0")
        f /= 2.0
    while f < 0.5:
        parts.append("atempo=0.5")
        f /= 0.5
    parts.append(f"atempo={f:.4f}")
    return parts


def _trim(ctx, p):
    start = _num("trim", p, "start", 0, lo=0)
    end = p.get("end")
    dur = p.get("duration")
    if end is not None and dur is not None:
        raise ValueError("'trim': give 'end' or 'duration', not both")
    if end is not None:
        end = _num("trim", p, "end", lo=0)
        if end <= start:
            raise ValueError("'trim': 'end' has to be after 'start'")
        ctx.duration = end - start
    elif dur is not None:
        ctx.duration = _num("trim", p, "duration", lo=0.01)
    ctx.start = start


def _speed(ctx, p):
    f = _num("speed", p, "factor", lo=0.25, hi=4)
    ctx.af.extend(_atempo_chain(f))


def _volume(ctx, p):
    ctx.af.append(f"volume={_num('volume', p, 'factor', lo=0, hi=5):.3f}")


def _normalize(ctx, p):
    # loudnorm, one pass: good enough for podcasts and voice notes
    target = _num("normalize", p, "target_lufs", -16, lo=-30, hi=-5)
    ctx.af.append(f"loudnorm=I={target:.1f}:TP=-1.5:LRA=11")


def _silence_trim(ctx, p):
    threshold = _num("silence_trim", p, "threshold_db", -45, lo=-80, hi=-10)
    ctx.af.append(
        f"silenceremove=start_periods=1:start_threshold={threshold:.0f}dB:"
        f"start_silence=0.1:stop_periods=-1:stop_threshold={threshold:.0f}dB:stop_silence=0.1"
    )


def _fade_in(ctx, p):
    d = _num("fade_in", p, "duration", lo=0.1, hi=30)
    ctx.af.append(f"afade=t=in:st=0:d={d:.2f}")


def _fade_out(ctx, p):
    d = _num("fade_out", p, "duration", lo=0.1, hi=30)
    ctx.af.append(f"afade=t=out:st=0:d={d:.2f}")


def _reverse(ctx, p):
    ctx.af.append("areverse")


def _convert(ctx, p):
    fmt = p.get("format", "mp3")
    if fmt not in CODECS:
        raise ValueError(f"'convert': format has to be one of {sorted(CODECS)}, got '{fmt}'")
    ctx.audio_format = fmt


def _mono(ctx, p):
    ctx.af.append("pan=mono|c0=0.5*c0+0.5*c1")


def _resample(ctx, p):
    rate = _int("resample", p, "rate", lo=8000, hi=192000)
    ctx.af.append(f"aresample={rate}")


def _bass(ctx, p):
    g = _num("bass", p, "gain_db", lo=-15, hi=15)
    ctx.af.append(f"bass=g={g:.1f}:f=100")


def _treble(ctx, p):
    g = _num("treble", p, "gain_db", lo=-15, hi=15)
    ctx.af.append(f"treble=g={g:.1f}:f=3000")


def _echo(ctx, p):
    # repeat the sound once, fading; like a room with bare walls
    delay = _num("echo", p, "delay_ms", 60, lo=10, hi=500)
    decay = _num("echo", p, "decay", 0.5, lo=0, hi=0.9)
    ctx.af.append(f"aecho=0.8:0.7:{delay:.0f}:{decay:.2f}")


OPS = {
    "trim": {"description": "Keep only start..end (seconds).", "params": {"start": {"type": "number", "default": 0, "min": 0}, "end": {"type": "number", "min": 0}, "duration": {"type": "number", "min": 0.01}}, "build": _trim},
    "speed": {"description": "Play faster or slower, pitch stays natural.", "params": {"factor": {"type": "number", "default": 1, "min": 0.25, "max": 4}}, "build": _speed},
    "volume": {"description": "Loudness, 0 to 5. 1 is unchanged, 0 is silence.", "params": {"factor": {"type": "number", "min": 0, "max": 5}}, "build": _volume},
    "normalize": {"description": "Even out the loudness to a target LUFS (podcasts: -16).", "params": {"target_lufs": {"type": "number", "default": -16, "min": -30, "max": -5}}, "build": _normalize},
    "silence_trim": {"description": "Cut silence off the start and the end.", "params": {"threshold_db": {"type": "number", "default": -45, "min": -80, "max": -10}}, "build": _silence_trim},
    "fade_in": {"description": "Fade in from silence.", "params": {"duration": {"type": "number", "min": 0.1, "max": 30}}, "build": _fade_in},
    "fade_out": {"description": "Fade out to silence at the end.", "params": {"duration": {"type": "number", "min": 0.1, "max": 30}}, "build": _fade_out},
    "reverse": {"description": "Play the audio backwards.", "params": {}, "build": _reverse},
    "convert": {"description": "Save as another format: mp3, wav, aac, ogg, flac or m4a.", "params": {"format": {"type": "string", "enum": sorted(CODECS), "default": "mp3"}}, "build": _convert},
    "mono": {"description": "Mix down to one channel.", "params": {}, "build": _mono},
    "resample": {"description": "Change the sample rate, e.g. 16000 for speech models.", "params": {"rate": {"type": "integer", "min": 8000, "max": 192000}}, "build": _resample},
    "bass": {"description": "Boost or cut the low end, -15 to 15 dB.", "params": {"gain_db": {"type": "number", "min": -15, "max": 15}}, "build": _bass},
    "treble": {"description": "Boost or cut the high end, -15 to 15 dB.", "params": {"gain_db": {"type": "number", "min": -15, "max": 15}}, "build": _treble},
    "echo": {"description": "One fading repeat, like a room with bare walls. Delay in ms, decay 0 to 0.9.", "params": {"delay_ms": {"type": "number", "default": 60, "min": 10, "max": 500}, "decay": {"type": "number", "default": 0.5, "min": 0, "max": 0.9}}, "build": _echo},
}


def list_ops():
    return {name: {"description": spec["description"], "params": spec["params"]} for name, spec in OPS.items()}


def build_ctx(ops):
    if not isinstance(ops, list) or not ops:
        raise ValueError("ops has to be a non-empty list, e.g. [{\"op\": \"trim\", \"start\": 2}]")
    ctx = Ctx()
    applied = []
    for item in ops:
        if not isinstance(item, dict) or "op" not in item:
            raise ValueError("every op needs an 'op' name, e.g. {\"op\": \"trim\", \"start\": 2}")
        name = item["op"]
        if name not in OPS:
            raise ValueError(f"unknown op '{name}'. Run 'audforge ops' to see them all.")
        OPS[name]["build"](ctx, item)
        applied.append(name)
    return ctx, applied


def probe(path):
    """ffprobe as a dict: duration, sample rate, channels, codec, format."""
    try:
        out = subprocess.run(
            [FFPROBE, "-v", "quiet", "-print_format", "json", "-show_streams", "-show_format", path],
            capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise ValueError(f"can't read '{path}': {e}")
    data = json.loads(out.stdout)
    info = {"duration": None, "sample_rate": None, "channels": None, "codec": None, "format": None}
    for s in data.get("streams", []):
        if s.get("codec_type") == "audio":
            info.update({
                "sample_rate": int(s["sample_rate"]) if s.get("sample_rate") else None,
                "channels": s.get("channels"),
                "codec": s.get("codec_name"),
            })
            break
    fmt = data.get("format", {})
    if fmt.get("duration"):
        info["duration"] = round(float(fmt["duration"]), 2)
    if fmt.get("format_name"):
        info["format"] = fmt["format_name"].split(",")[0]
    return info
