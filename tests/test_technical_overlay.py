from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import technical_overlay


class TechnicalOverlayTests(unittest.TestCase):
    def test_blueprint_asset_is_svg_with_expected_viewbox(self):
        asset = ROOT / "assets" / "blueprint" / "automotive_blueprint.svg"
        self.assertTrue(asset.is_file())
        text = asset.read_text(encoding="utf-8")
        self.assertIn('<svg xmlns="http://www.w3.org/2000/svg"', text)
        self.assertIn('viewBox="0 0 1600 900"', text)
        self.assertIn("stroke=\"white\"", text)
        self.assertIn("opacity=\"0.9\"", text)

    def test_filter_command_keeps_base_duration_with_looped_blueprint(self):
        if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
            self.skipTest("ffmpeg/ffprobe unavailable")
        scenes = [{
            "text_en": "This scene explains automotive engine performance and why the mechanism matters for reliability and control.",
            "technical_component": "engine system",
            "technical_flow": "airflow to power output",
            "technical_motion": "components moving",
            "spec_status": "GENERAL_EXPLANATION",
            "section": "performance",
        }]
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            source = tmp / "source.mp4"
            output = tmp / "output.mp4"
            run_dir = tmp / "run"
            subprocess.run([
                "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=25",
                "-t", "2", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            with patch.object(technical_overlay, "RUN", run_dir):
                technical_overlay._process(source, output, scenes, vertical=False)
            duration = technical_overlay._duration(output)
            self.assertGreaterEqual(duration, 1.9)
            self.assertLessEqual(duration, 2.1)
            probe = subprocess.run([
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=pix_fmt", "-of", "default=nw=1:nk=1", str(output)
            ], check=True, capture_output=True, text=True)
            self.assertEqual(probe.stdout.strip(), "yuv420p")


if __name__ == "__main__":
    unittest.main()
