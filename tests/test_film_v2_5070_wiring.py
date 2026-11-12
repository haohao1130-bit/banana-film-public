"""RTX 5070 F-drive static wiring contracts (does not require Windows or a GPU)."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Local5070WiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.boot = (ROOT / "tools/bootstrap_film_v2_5070.ps1").read_text(encoding="utf-8")
        cls.launcher_source = (ROOT / "tools/start_film_v2_5070.ps1").read_text(encoding="utf-8")
        cls.cmd = (ROOT / "Start_BANANA_FILM_5070.cmd").read_text(encoding="utf-8")
        cls.html = (ROOT / "film_v2/web/index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "film_v2/web/app.js").read_text(encoding="utf-8")
        cls.server = (ROOT / "film_v2/server.py").read_text(encoding="utf-8")

    def test_f_drive_is_authoritative_for_uploads_and_outputs(self):
        self.assertIn(r"F:\BANANA_FILM_5070_STUDIO\Media", self.launcher_source)
        self.assertIn("BANANA_DATA=$DataRoot", self.launcher_source)
        for folder in ("library", "videos", "films_v2", "logs"):
            self.assertIn("'" + folder + "'", self.launcher_source)
        self.assertIn("Join-Path $InstallRoot 'Media'", self.boot)

    def test_local_port_not_mv_or_colab(self):
        self.assertIn("[int]$Port=8195", self.launcher_source)
        self.assertIn("[int]$Port=8195", self.boot)
        self.assertIn("BANANA_PORT=[string]$Port", self.launcher_source)
        self.assertIn("'rtx5070-fdrive'", self.launcher_source)
        self.assertIn('"rtx5070-fdrive"', self.server)
        self.assertIn('"data_root"', self.server)
        self.assertIn("$reportedRoot", self.launcher_source)

    def test_fixed_flat_branch_and_public_origin_only(self):
        self.assertIn("film-v2-rtx5070-fdrive", self.boot)
        self.assertIn("banana-film-public.git", self.boot)
        self.assertNotIn("banana-film-studio.git", self.boot)
        self.assertIn("pull --ff-only", self.boot)
        self.assertNotIn("reset --hard", self.boot)
        self.assertNotIn("git clean", self.boot)
        self.assertIn("Bootstrap_BANANA_FILM_5070.ps1", self.cmd)

    def test_rtx_cu130_and_original_h3_model_reuse(self):
        self.assertIn("torch.version.cuda.startswith", self.launcher_source)
        self.assertIn('"13"', self.launcher_source)
        self.assertIn("MiniMaxH3ReferenceToVideo", self.launcher_source)
        self.assertIn("MiniMaxH3AddGuide", self.launcher_source)
        self.assertIn("'--lowvram'", self.launcher_source)
        self.assertIn("ComfyBase", self.launcher_source)
        self.assertNotIn("pip install", self.launcher_source)
        self.assertNotIn("huggingface_hub", self.launcher_source)

    def test_ui_defaults_to_six_second_480p_independent_for_12gb(self):
        self.assertIn('value="6" selected', self.html)
        self.assertIn('value="independent" selected', self.html)
        self.assertIn('value="480p" selected', self.html)
        self.assertIn('id="output-video-path"', self.html)
        self.assertIn("job.output_video", self.js)


if __name__ == "__main__":
    unittest.main()
