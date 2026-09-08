from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SELECT_PRODUCT = SKILL_DIR / "scripts" / "select_product.py"
CREATE_RUN = SKILL_DIR / "scripts" / "create_run.py"


class ProductSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.workspace = self.root / "workspace.yaml"
        self.workspace.write_text(
            "product_library: ./products\noutput_root: ./runs\n", encoding="utf-8"
        )
        products = self.root / "products"
        products.mkdir()
        (products / "catalog.yaml").write_text(
            "default_sku: T10P\n"
            "products:\n"
            "  - sku: T10P\n"
            "    path: ./T10P\n"
            "  - sku: TB02\n"
            "    path: ./TB02\n"
            "  - sku: TAB10\n"
            "    path: ./custom-tab10\n"
            "  - sku: DRAFT\n"
            "    path: ./not-created-yet\n"
            "    enabled: false\n",
            encoding="utf-8",
        )
        self.write_product(products / "T10P", "T10P", "T10P Tablet", ["主推款"])
        self.write_product(products / "TB02", "TB02", "TB02 Tablet", ["TB02套装"])
        self.write_product(
            products / "custom-tab10", "TAB10", "TAB10 Tablet", ["TAB10套装"]
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @staticmethod
    def write_product(path: Path, sku: str, name: str, aliases: list[str]) -> None:
        path.mkdir()
        (path / "product.yaml").write_text(
            f"sku: {sku}\n"
            f"product_name: {name}\n"
            f"aliases: [{', '.join(aliases)}]\n"
            "bundle_includes: [tablet]\n"
            "allowed_claims: [test]\n"
            "forbidden_claims: [test]\n",
            encoding="utf-8",
        )

    def run_selector(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SELECT_PRODUCT),
                "--workspace",
                str(self.workspace),
                *args,
            ],
            capture_output=True,
            text=True,
        )

    def test_uses_default_when_sku_is_omitted(self) -> None:
        result = self.run_selector()
        self.assertEqual(result.returncode, 0, result.stdout)
        selected = json.loads(result.stdout)
        self.assertEqual(selected["sku"], "T10P")
        self.assertEqual(selected["resolution"], "default")

    def test_resolves_product_alias_to_canonical_sku(self) -> None:
        result = self.run_selector("--sku", "TAB10套装")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(result.stdout)["sku"], "TAB10")

    def test_lists_enabled_products(self) -> None:
        result = self.run_selector("--list")
        self.assertEqual(result.returncode, 0, result.stdout)
        products = json.loads(result.stdout)["products"]
        self.assertEqual(
            [item["sku"] for item in products], ["T10P", "TB02", "TAB10"]
        )

    def test_create_run_records_canonical_sku_for_alias(self) -> None:
        source = self.root / "source.mp4"
        source.write_bytes(b"video")
        result = subprocess.run(
            [
                sys.executable,
                str(CREATE_RUN),
                "--workspace",
                str(self.workspace),
                "--sku",
                "TB02套装",
                "--source",
                str(source),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        run_dir = Path(result.stdout.strip())
        record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(record["sku"], "TB02")
        self.assertEqual(record["requested_sku"], "TB02套装")
        self.assertEqual(record["run_mode"], "REVIEW_INCREMENTAL")
        self.assertEqual(record["delivery_plan"], [])

    def test_create_batch_run_prepares_six_delivery_states(self) -> None:
        source = self.root / "source.mp4"
        source.write_bytes(b"video")
        result = subprocess.run(
            [
                sys.executable,
                str(CREATE_RUN),
                "--workspace",
                str(self.workspace),
                "--sku",
                "TAB10",
                "--mode",
                "batch",
                "--source",
                str(source),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        run_dir = Path(result.stdout.strip())
        record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        script_ids = ["BASE", "V01", "V02", "V03", "V04", "V05"]
        self.assertEqual(record["run_mode"], "DIRECT_BATCH")
        self.assertEqual(record["delivery_plan"], script_ids)
        self.assertEqual(
            record["deliveries"],
            {script_id: {"status": "pending"} for script_id in script_ids},
        )

    def test_unknown_sku_reports_available_choices(self) -> None:
        result = self.run_selector("--sku", "missing")
        self.assertEqual(result.returncode, 2)
        self.assertIn("可选 SKU：T10P、TB02、TAB10", result.stdout)


if __name__ == "__main__":
    unittest.main()
