# Contributing

audforge grows by adding operations. An operation is one function in `audforge/ops.py` plus one entry in the `OPS` dict: name, a one-line description, and a params schema (type, default, min/max or enum).

Rules:

- One op does one thing. Keep it under 15 lines if you can.
- Never break the JSON contract: `audforge ops` must keep working, and every op must run on files with any sample rate and channel count.
- Add a test in `tests/test_ops.py` that runs the op on the fixture audio.
- Run `python -m unittest` before opening a PR.

That's it.
