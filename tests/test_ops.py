"""Tests run against small generated audio, no fixtures needed."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from audforge import apply_ops, describe, join_audios, list_ops, transcribe  # noqa: E402


def _make_tone(path, duration=4):
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
         "-ac", "2", "-c:a", "libmp3lame", path],
        check=True,
    )


def _make_with_silence(path):
    # 1s of silence, then 1s of tone
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "aevalsrc=0:d=1",
         "-f", "lavfi", "-i", "sine=frequency=440:d=1",
         "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1",
         "-c:a", "pcm_s16le", path],
        check=True,
    )


class TestAudforge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.tone = os.path.join(cls.tmp, "tone.mp3")
        _make_tone(cls.tone)
        cls.silence = os.path.join(cls.tmp, "silence.wav")
        _make_with_silence(cls.silence)

    def out(self, name):
        return os.path.join(self.tmp, name)

    def test_ops_list(self):
        ops = list_ops()
        self.assertGreaterEqual(len(ops), 12)
        self.assertIn("trim", ops)
        self.assertIn("normalize", ops)
        self.assertIn("silence_trim", ops)

    def test_describe(self):
        info = describe(self.tone)
        self.assertAlmostEqual(info["duration"], 4, delta=0.3)
        self.assertEqual(info["channels"], 2)
        self.assertEqual(info["sample_rate"], 44100)
        self.assertEqual(info["codec"], "mp3")

    def test_trim(self):
        out = apply_ops(self.tone, self.out("t.mp3"),
                        [{"op": "trim", "start": 1, "end": 3}])
        self.assertAlmostEqual(out["duration"], 2, delta=0.3)

    def test_speed(self):
        out = apply_ops(self.tone, self.out("s.mp3"), [{"op": "speed", "factor": 2}])
        self.assertAlmostEqual(out["duration"], 2, delta=0.3)

    def test_volume_and_fades(self):
        out = apply_ops(self.tone, self.out("v.mp3"),
                        [{"op": "volume", "factor": 0.5},
                         {"op": "fade_in", "duration": 0.5},
                         {"op": "fade_out", "duration": 0.5}])
        self.assertAlmostEqual(out["duration"], 4, delta=0.3)
        self.assertTrue(os.path.getsize(self.out("v.mp3")) > 1000)

    def test_normalize(self):
        out = apply_ops(self.tone, self.out("n.mp3"),
                        [{"op": "normalize", "target_lufs": -16}])
        self.assertAlmostEqual(out["duration"], 4, delta=0.5)
        self.assertTrue(os.path.getsize(self.out("n.mp3")) > 1000)

    def test_silence_trim(self):
        out = apply_ops(self.silence, self.out("st.wav"), [{"op": "silence_trim"}])
        self.assertAlmostEqual(out["duration"], 1, delta=0.4)

    def test_reverse(self):
        out = apply_ops(self.tone, self.out("rev.mp3"), [{"op": "reverse"}])
        self.assertAlmostEqual(out["duration"], 4, delta=0.3)

    def test_convert_and_resample(self):
        out = apply_ops(self.tone, self.out("c.wav"),
                        [{"op": "convert", "format": "wav"},
                         {"op": "resample", "rate": 16000}])
        self.assertEqual(out["format"], "wav")
        self.assertEqual(out["sample_rate"], 16000)
        self.assertTrue(os.path.getsize(self.out("c.wav")) > 1000)

    def test_mono_bass_treble(self):
        out = apply_ops(self.tone, self.out("m.mp3"),
                        [{"op": "mono"}, {"op": "bass", "gain_db": 3},
                         {"op": "treble", "gain_db": -2}])
        self.assertEqual(out["channels"], 1)
        self.assertTrue(os.path.getsize(self.out("m.mp3")) > 1000)

    def test_join(self):
        out = join_audios([self.tone, self.tone], self.out("joined.mp3"))
        self.assertAlmostEqual(out["duration"], 8, delta=0.5)

    def test_unknown_op_and_bad_param(self):
        with self.assertRaises(ValueError):
            apply_ops(self.tone, self.out("x.mp3"), [{"op": "nope"}])
        with self.assertRaises(ValueError):
            apply_ops(self.tone, self.out("x.mp3"), [{"op": "volume", "factor": 9}])
        with self.assertRaises(ValueError):
            apply_ops(self.tone, self.out("x.mp3"), [{"op": "trim", "start": 3, "end": 1}])
        with self.assertRaises(ValueError):
            apply_ops(self.tone, self.out("x.mp3"), [{"op": "convert", "format": "flac2"}])

    @unittest.skipUnless(shutil.which("whisper"), "whisper CLI not installed")
    def test_transcribe_missing_file(self):
        with self.assertRaises(ValueError):
            transcribe(os.path.join(self.tmp, "nope.mp3"))

    def test_transcribe_without_whisper(self):
        if shutil.which("whisper"):
            self.skipTest("whisper is installed, nothing to check here")
        with self.assertRaises(RuntimeError):
            transcribe(self.tone)

    def test_cli(self):
        res = subprocess.run([sys.executable, "-m", "audforge.cli", "ops"],
                             capture_output=True, text=True, cwd=os.path.join(os.path.dirname(__file__), ".."))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertGreaterEqual(len(json.loads(res.stdout)), 12)


if __name__ == "__main__":
    unittest.main()
