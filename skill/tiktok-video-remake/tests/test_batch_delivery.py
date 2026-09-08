from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
MANAGE_DELIVERY = SKILL_DIR / "scripts" / "manage_delivery_branch.py"
SCRIPT_IDS = ("BASE", "V01", "V02", "V03", "V04", "V05")


class BatchDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.temp_dir.name) / "run"
        self.run_dir.mkdir()
        self.review = self.run_dir / "01-analysis" / "script-review.md"
        self.review.parent.mkdir()
        variants = "\n".join(
            f"## {script_id}｜版本 {script_id}\n\n**逐镜覆盖**\n\n- S01：保持。"
            for script_id in SCRIPT_IDS[1:]
        )
        self.review.write_text(
            "# 复刻执行脚本（原样复刻，独立可执行）\n\n"
            "- S01｜0–10 秒：测试画面。\n\n"
            "# 变体母版\n\n"
            f"{variants}\n",
            encoding="utf-8",
        )
        record = {
            "run_id": "run",
            "sku": "TB02",
            "run_mode": "DIRECT_BATCH",
            "delivery_plan": list(SCRIPT_IDS),
            "status": "created",
            "current_script": None,
            "deliveries": {
                script_id: {"status": "pending"} for script_id in SCRIPT_IDS
            },
        }
        (self.run_dir / "run.json").write_text(
            json.dumps(record, ensure_ascii=False), encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def manage(self, action: str, script_id: str, *extra: str) -> None:
        subprocess.run(
            [
                sys.executable,
                str(MANAGE_DELIVERY),
                action,
                str(self.run_dir),
                str(self.review),
                script_id,
                *extra,
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    def create_outputs(self, script_id: str) -> None:
        storyboard = self.run_dir / "02-storyboard" / script_id
        symphony = self.run_dir / "03-symphony" / script_id
        storyboard.mkdir(parents=True, exist_ok=True)
        symphony.mkdir(parents=True, exist_ok=True)
        (storyboard / "storyboard-grid-b1.png").write_bytes(b"image")
        (symphony / "symphony-prompt.txt").write_text("prompt", encoding="utf-8")

    def record(self) -> dict:
        return json.loads((self.run_dir / "run.json").read_text(encoding="utf-8"))

    def test_failed_branch_is_recorded_for_resume(self) -> None:
        self.manage("start", "BASE")
        self.create_outputs("BASE")
        self.manage("complete", "BASE")
        self.manage("start", "V01")
        self.manage("fail", "V01", "--reason", "宫格生成失败")

        record = self.record()
        self.assertEqual(record["status"], "batch_partial_failure")
        self.assertEqual(record["deliveries"]["BASE"]["status"], "complete")
        self.assertEqual(record["deliveries"]["V01"]["status"], "failed")
        self.assertEqual(record["deliveries"]["V01"]["last_error"], "宫格生成失败")
        summary = (self.run_dir / "delivery-summary.md").read_text(encoding="utf-8")
        self.assertIn("| BASE | 原样复刻 | complete |", summary)
        self.assertIn("| V01 | 版本 V01 | failed |", summary)
        self.assertIn("宫格生成失败", summary)

    def test_six_completed_branches_finish_batch(self) -> None:
        for script_id in SCRIPT_IDS:
            self.manage("start", script_id)
            self.create_outputs(script_id)
            self.manage("complete", script_id)

        record = self.record()
        self.assertEqual(record["status"], "complete")
        self.assertTrue(
            all(
                record["deliveries"][script_id]["status"] == "complete"
                for script_id in SCRIPT_IDS
            )
        )
        summary = (self.run_dir / "delivery-summary.md").read_text(encoding="utf-8")
        self.assertIn("- 状态：complete", summary)


if __name__ == "__main__":
    unittest.main()
