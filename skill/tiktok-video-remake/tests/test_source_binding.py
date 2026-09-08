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
NORMALIZE_SOURCE = SKILL_DIR / "scripts" / "normalize_source_duration.py"


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
        product_dir = self.root / "product-library" / "T10P"
        product_dir.mkdir(parents=True)
        (self.root / "product-library" / "catalog.yaml").write_text(
            "default_sku: T10P\n"
            "products:\n"
            "  - sku: T10P\n"
            "    path: ./T10P\n",
            encoding="utf-8",
        )
        (product_dir / "product.yaml").write_text(
            "sku: T10P\n"
            "product_name: Test Tablet\n"
            "aliases: [测试平板]\n"
            "bundle_includes: [tablet]\n"
            "allowed_claims: [test]\n"
            "forbidden_claims: [test]\n",
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
    def test_overlong_source_is_trimmed_and_rebound(self) -> None:
        source = self.root / "long.mov"
        subprocess.run(
            [
                shutil.which("ffmpeg"),
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=red:s=64x64:d=15.5",
                "-c:v",
                "mpeg4",
                "-pix_fmt",
                "yuv420p",
                str(source),
            ],
            check=True,
        )
        original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        run_dir = self.create_run(source)

        result = subprocess.run(
            [sys.executable, str(NORMALIZE_SOURCE), str(run_dir)],
            check=True,
            capture_output=True,
            text=True,
        )

        record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        rebound = run_dir / record["source_video"]["input_path"]
        self.assertIn("TRIMMED:", result.stdout)
        self.assertEqual(rebound.name, "source.mp4")
        self.assertTrue(record["source_video"]["trimmed"])
        self.assertEqual(record["source_video"]["trim_range_seconds"], [0, 15.0])
        self.assertEqual(record["source_video"]["original_sha256"], original_hash)
        self.assertEqual(record["source_video"]["sha256"], hashlib.sha256(rebound.read_bytes()).hexdigest())
        self.assertLessEqual(record["source_video"]["duration_seconds"], 15.05)
        self.assertFalse((run_dir / "00-input" / "source.mov").exists())

        prepared = run_dir / "01-analysis" / "prepared"
        subprocess.run(
            [
                sys.executable,
                str(PREPARE_VIDEO),
                str(rebound),
                str(prepared),
                "--run-dir",
                str(run_dir),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

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
