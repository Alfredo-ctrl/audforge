"""Run ffmpeg. One call per edit, JSON-friendly errors."""

import os
import shutil
import subprocess
import tempfile

from forge_common.ffmpeg import concat_list, fade_out_at, run
from .ops import CODECS, FFMPEG, build_ctx, probe

_WHISPER_MODELS = ("tiny", "base", "small", "medium", "large")


def _codec_for(output_path, ctx):
    if ctx.audio_format:
        return CODECS[ctx.audio_format]
    ext = os.path.splitext(output_path)[1].lstrip(".").lower()
    return CODECS.get(ext, "aac")


def apply_ops(input_path, output_path, ops):
    ctx, applied = build_ctx(ops)
    info_in = probe(input_path)

    # fade_out starts duration seconds before the end, so build the filter
    # now that the clip length is known, instead of patching a st=0 filter
    if ctx.mono and info_in.get("channels") != 1:
        ctx.af.append("pan=mono|c0=0.5*c0+0.5*c1")
    if ctx.fade_out_durations:
        total = ctx.duration if ctx.duration is not None else info_in["duration"]
        if total is None:
            raise ValueError(f"can't fade out '{input_path}': unknown duration")
        for d in ctx.fade_out_durations:
            ctx.af.append(fade_out_at("audio", d, total))

    cmd = [FFMPEG, "-y", "-v", "error"]
    if ctx.start is not None:
        cmd += ["-ss", str(ctx.start)]
    if ctx.duration is not None:
        cmd += ["-t", str(ctx.duration)]
    cmd += ["-i", input_path]
    if ctx.af:
        cmd += ["-af", ",".join(ctx.af)]
    cmd += ["-c:a", _codec_for(output_path, ctx), output_path]
    run(cmd)

    out = {"output": output_path, "ops_applied": applied}
    out.update(probe(output_path))
    return out


def join_audios(inputs, output_path):
    """Stick audio files together, in order. Re-encodes so mixed files still join."""
    if len(inputs) < 2:
        raise ValueError("join needs at least 2 audio files")
    for p in inputs:
        probe(p)
    list_path = concat_list(inputs)
    ext = os.path.splitext(output_path)[1].lstrip(".").lower()
    try:
        run([FFMPEG, "-y", "-v", "error", "-f", "concat", "-safe", "0",
             "-i", list_path, "-c:a", CODECS.get(ext, "aac"), output_path])
    finally:
        os.unlink(list_path)
    return {"output": output_path, "inputs": inputs, **probe(output_path)}


def describe(path):
    return probe(path)


def transcribe(input_path, model="tiny", language=None):
    """Transcribe with local Whisper (openai-whisper CLI). Needs `whisper` installed.

    Returns {"text": ..., "model": ..., "language": ...}.
    """
    if model not in _WHISPER_MODELS:
        raise ValueError(f"'transcribe': model has to be one of {", ".join(_WHISPER_MODELS)}, got '{model}'")
    if shutil.which("whisper") is None:
        raise RuntimeError(
            "whisper isn't installed on this machine. Install it with "
            "'pip install openai-whisper' (it needs ffmpeg too) and try again."
        )
    probe(input_path)
    tmp = tempfile.mkdtemp(prefix="audforge-transcribe-")
    try:
        base = os.path.splitext(os.path.basename(input_path))[0]
        cmd = ["whisper", input_path, "--model", model, "--output_format", "txt",
               "--output_dir", tmp, "--fp16", "False", "--verbose", "False"]
        if language:
            cmd += ["--language", language]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            tail = " ".join((res.stderr or "").strip().splitlines()[-3:])
            raise RuntimeError(f"whisper failed: {tail[:500] or 'unknown error'}")
        txt_path = os.path.join(tmp, base + ".txt")
        with open(txt_path, encoding="utf-8") as f:
            text = f.read().strip()
        return {"text": text, "model": model, "language": language, "input": input_path}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
