from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
CREATE_RUN = SKILL_DIR / "scripts" / "create_run.py"
PREPARE_VIDEO = SKILL_DIR / "scripts" / "prepare_video.py"


class SourceBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.workspace = self.root / "workspace.yaml"
        self.workspace.write_text(
            "product_library: ./product-library\n"
            "output_root: ./runs\n"
            "generation:\n"
            "  max_clip_seconds: 15\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def create_run(self, source: Path) -> Path:
        result = subprocess.run(
            [
                sys.executable,
                str(CREATE_RUN),
                "--workspace",
                str(self.workspace),
                "--sku",
                "T10P",
                "--label",
                "video-b",
                "--source",
                str(source),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return Path(result.stdout.strip())

    def test_create_run_copies_and_records_the_source_video(self) -> None:
        source = self.root / "Video B.MP4"
        source.write_bytes(b"video-b")

        run_dir = self.create_run(source)

        copied_source = run_dir / "00-input" / "source.mp4"
        record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(copied_source.read_bytes(), b"video-b")
        self.assertEqual(
            record["source_video"],
            {
                "original_name": "Video B.MP4",
                "input_path": "00-input/source.mp4",
                "sha256": hashlib.sha256(b"video-b").hexdigest(),
                "size_bytes": 7,
            },
        )

    def test_prepare_rejects_a_video_from_another_run(self) -> None:
        source_a = self.root / "A.mp4"
        source_b = self.root / "B.mp4"
        source_a.write_bytes(b"video-a")
        source_b.write_bytes(b"video-b")
        run_a = self.create_run(source_a)
        run_b = self.create_run(source_b)

        result = subprocess.run(
            [
                sys.executable,
                str(PREPARE_VIDEO),
                str(run_a / "00-input" / "source.mp4"),
                str(run_b / "01-analysis" / "prepared"),
                "--run-dir",
                str(run_b),
            ],
            capture_output=True,
            text=True,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("源视频不属于当前 run", result.stderr)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "需要 FFmpeg")
    def test_preparing_a_silent_video_removes_stale_audio(self) -> None:
        source = self.root / "B.mp4"
        subprocess.run(
            [
                shutil.which("ffmpeg"),
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=180x320:d=0.5",
                "-c:v",
                "mpeg4",
                "-pix_fmt",
                "yuv420p",
                str(source),
            ],
            check=True,
        )
        run_dir = self.create_run(source)
        prepared = run_dir / "01-analysis" / "prepared"
        stale_audio = prepared / "audio-analysis.wav"
        stale_audio.parent.mkdir(parents=True, exist_ok=True)
        stale_audio.write_bytes(b"audio-from-video-a")

        subprocess.run(
            [
                sys.executable,
                str(PREPARE_VIDEO),
                str(run_dir / "00-input" / "source.mp4"),
                str(prepared),
                "--run-dir",
                str(run_dir),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        metadata = json.loads((prepared / "metadata.json").read_text(encoding="utf-8"))
        self.assertFalse(stale_audio.exists())
        self.assertFalse(metadata["has_audio"])
        self.assertEqual(metadata["source_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
