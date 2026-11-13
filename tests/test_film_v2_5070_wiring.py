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
        cls.installer = (ROOT / "Install_Shortcut.ps1").read_text(encoding="utf-8")
        cls.install_cmd = (ROOT / "Install_Desktop_Shortcut.cmd").read_text(encoding="utf-8")
        cls.html = (ROOT / "film_v2/web/index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "film_v2/web/app.js").read_text(encoding="utf-8")
        cls.server = (ROOT / "film_v2/server.py").read_text(encoding="utf-8")
        cls.local_server = (ROOT / "film_v2/local_classic_server.py").read_text(encoding="utf-8")
        cls.local_version_js = (ROOT / "film_v2/web/build_5070.js").read_text(encoding="utf-8")

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
        self.assertIn("settings.json", self.boot)
        self.assertIn("ComfyInputDir", self.boot)
        self.assertIn("PythonPath", self.boot)
        self.assertNotIn("reset --hard", self.boot)
        self.assertNotIn("git clean", self.boot)
        self.assertIn("Bootstrap_BANANA_FILM_5070.ps1", self.cmd)

    def test_v4_installer_and_pinned_f_drive_shortcut(self):
        self.assertIn("F:\\BANANA_FILM_5070_STUDIO", self.installer)
        self.assertIn("BANANA FILM 5070 STUDIO.lnk", self.installer)
        self.assertIn("Bootstrap_BANANA_FILM_5070.ps1", self.installer)
        self.assertIn("Install_Shortcut.ps1", self.install_cmd)
        self.assertIn("-NoExit -ExecutionPolicy Bypass -File", self.installer)
        self.assertNotIn("BananaMV5070'", self.installer)
        self.assertNotIn("reset --hard", self.installer)

    def test_v4_separates_cuda_13_comfy_from_backend_python(self):
        self.assertNotIn("& $python -c", self.launcher_source)
        self.assertIn("tools\\check_film_cuda13.py", self.launcher_source)
        self.assertIn("$probe --role backend", self.launcher_source)
        self.assertIn("$probe --role comfy", self.launcher_source)
        self.assertIn("Banana9B-cu130", self.launcher_source)
        self.assertIn("Start-Process -FilePath $comfyPython", self.launcher_source)
        self.assertIn("Start-Process -FilePath $python", self.launcher_source)
        probe = (ROOT / "tools/check_film_cuda13.py").read_text(encoding="utf-8")
        self.assertIn('cuda.startswith("13")', probe)
        self.assertIn('if args.role == "backend"', probe)
        self.assertIn("torch.cuda.is_available()", probe)
        self.assertIn("import PIL", probe)
        self.assertIn("import numpy", probe)
        self.assertIn("MiniMaxH3ReferenceToVideo", self.launcher_source)
        self.assertIn("MiniMaxH3AddGuide", self.launcher_source)
        self.assertIn("'--lowvram'", self.launcher_source)
        self.assertIn("ComfyBase", self.launcher_source)
        self.assertNotIn("pip install", self.launcher_source)
        self.assertNotIn("huggingface_hub", self.launcher_source)


    def test_v4_auto_update_and_real_backend_build_label(self):
        self.assertIn("pull --ff-only", self.boot)
        self.assertIn("Keeping existing local version", self.boot)
        self.assertIn("Handing off to the updated F-drive launcher", self.boot)
        self.assertIn("$canonicalBootstrap", self.boot)
        self.assertIn("server_process.json", self.launcher_source)
        self.assertIn("expectedCommit", self.launcher_source)
        self.assertIn("health.version.commit", self.launcher_source)
        self.assertIn("health.busy", self.launcher_source)
        self.assertIn("Get-CimInstance Win32_Process", self.launcher_source)
        self.assertIn("film_v2.local_classic_server", self.launcher_source)
        self.assertIn("Stop-Process -Id $ownerPid", self.launcher_source)
        self.assertIn("def detect_build_version()", self.local_server)
        self.assertIn('"version": SERVER_BUILD', self.local_server)
        self.assertIn('"instance": SERVER_INSTANCE', self.local_server)
        self.assertIn('"busy": app.GPU_LOCK.locked()', self.local_server)
        self.assertIn("film5070-version", self.local_version_js)
        self.assertIn("refreshVersion", self.local_version_js)
        self.assertIn("cache:\'no-store\'", self.local_version_js)
        self.assertIn("health.version", self.local_version_js)

    def test_full_film_defaults_and_optional_features(self):
        self.assertIn('value="30" selected', self.html)
        self.assertIn('value="15" selected', self.html)
        self.assertIn('value="chain5" selected', self.html)
        self.assertNotIn('value="6" selected', self.html)
        self.assertNotIn('value="independent" selected', self.html)
        for film_length in (15, 30, 60, 90, 120, 180):
            self.assertIn(f'value="{film_length}"', self.html)
        for segment_length in (6, 10, 15):
            self.assertIn(f'value="{segment_length}"', self.html)
        for mode in ("chain5", "chain", "independent"):
            self.assertIn(f'value="{mode}"', self.html)
        self.assertIn('value="480p" selected', self.html)
        self.assertIn('value="720p"', self.html)
        self.assertIn('value="dialogue"', self.html)
        self.assertIn('id="output-video-path"', self.html)
        self.assertIn("job.output_video", self.js)


if __name__ == "__main__":
    unittest.main()
