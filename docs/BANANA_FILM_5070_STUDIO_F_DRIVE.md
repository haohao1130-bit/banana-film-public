# BANANA FILM 5070 STUDIO | RTX 5070 F-drive edition

**Public experiment branch:** film-v2-rtx5070-fdrive
**Source architecture:** public Python-Owned Film V2 from film-v2-python-owned-public-20261112.
**Isolation:** Does NOT change public main, older film, existing MV or the GPU model files.

## Storage layout on F:

Default root is F:\BANANA_FILM_5070_STUDIO.

| Location | Purpose |
| --- | --- |
| F:\BANANA_FILM_5070_STUDIO\Launcher | Persisted one-click launcher and desktop shortcut target |
| F:\BANANA_FILM_5070_STUDIO\App | Branch-specific Git checkout; fast-forward updates only |
| F:\BANANA_FILM_5070_STUDIO\Media\library | Original uploaded images (canonical archive) |
| F:\BANANA_FILM_5070_STUDIO\Media\videos | Exported full MP4 videos |
| F:\BANANA_FILM_5070_STUDIO\Media\films_v2 | Screenplays, current state, sources, native AV segment files, retakes, immutable masters |
| F:\BANANA_FILM_5070_STUDIO\Media\logs | Backend and, when started by launcher, ComfyUI logs |
| F:\BANANA_FILM_5070_STUDIO\Media\comfy_input | Comfy input cache when this launcher starts ComfyUI |
| F:\BANANA_FILM_5070_STUDIO\Media\comfy_output | Comfy output when this launcher starts ComfyUI |
| F:\BANANA_FILM_5070_STUDIO\Media\comfy_temp | Comfy temporary output when this launcher starts ComfyUI |

**Important:** When an already-running ComfyUI is reused, its input directory is not relocated without restarting it. Uploaded original photos and final MP4 stay on F:, but a working picture copy may be placed in the already-running ComfyUI input (often on C:). To keep Comfy caches on F: too, first close existing ComfyUI and let the dedicated launcher start ComfyUI with F: input/output/temp and --lowvram. Models stay in their original directories either way.

## One-click installer

1. Download the BANANA_FILM_5070_STUDIO_F_DRIVE_LAUNCHER.zip package and **extract it**.
2. Double-click Start_BANANA_FILM_5070.cmd.
3. It checks the F: drive and Git, clones or fast-forward-updates this exact PUBLIC experimental branch under F:\BANANA_FILM_5070_STUDIO\App and creates the persistent desktop shortcut "BANANA FILM 5070 STUDIO".
4. The application checks existing CUDA13 Torch, Pillow/numpy, ffmpeg/ffprobe and H3/9B ComfyUI nodes; it does not reinstall models or Torch.
5. The browser opens http://127.0.0.1:8195 . The UI shows the absolute F: file path after an MP4 is exported.

Alternative manual checkout in PowerShell:

    git clone --branch film-v2-rtx5070-fdrive --single-branch https://github.com/haohao1130-bit/banana-film-public.git F:\BANANA_FILM_5070_STUDIO\App
    powershell -NoProfile -ExecutionPolicy Bypass -File F:\BANANA_FILM_5070_STUDIO\App\tools\bootstrap_film_v2_5070.ps1

The launcher does not reset, clean or overwrite a Git checkout containing tracked edits. It will not delete archived assets or old jobs.

Custom ComfyBase, ComfySource, ComfyInputDir and PythonPath overrides are saved at F:\\BANANA_FILM_5070_STUDIO\\Launcher\\settings.json. Next desktop launch reuses them; command-line overrides update the saved paths. This file contains paths and a local port only, never credentials or model weights.

## Existing RTX 5070 / CUDA13 configuration

The installer preferentially reuses your working Windows paths:
- ComfyUI API: http://127.0.0.1:8000
- ComfyUI model base: %USERPROFILE%\Documents\ComfyUI
- ComfyUI source: %LOCALAPPDATA%\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI
- Python: first %USERPROFILE%\Documents\ComfyUI\.venv\Scripts\python.exe, then %LOCALAPPDATA%\Banana9B-cu130\Scripts\python.exe
- Must have TextGenerate, MiniMaxH3ReferenceToVideo, VAEDecodeAudio, and for Chain5 MiniMaxH3AddGuide.
- If no Comfy process exists and Comfy source is present, the launcher starts it with --lowvram, --preview-method none and F: input/output/temp, while reusing original model locations.
- If already running, its flags and model locations are untouched.

If you move ComfyUI later, adjust explicitly:

    powershell -NoProfile -ExecutionPolicy Bypass -File F:\BANANA_FILM_5070_STUDIO\Launcher\Bootstrap_BANANA_FILM_5070.ps1 -ComfyBase "D:\ComfyData" -ComfySource "D:\ComfySrc" -PythonPath "D:\ComfyData\.venv\Scripts\python.exe" -ComfyInputDir "D:\ComfyData\input"

Custom ComfyUrl and NoAutoComfy switches are also supported. Always set ComfyInputDir to the real input folder when reusing an externally started ComfyUI.

## Recommended tests (RTX5070 12GB)

- **Full-function default:** 30-second film ceiling, 15-second clip ceiling, 480p, Chain5; no arbitrary 6-second limit is enabled. The full 15/30/60/90/120/180-second film choices remain available, up to a hard 180 seconds.
- **Clip choices:** 6, 10 or 15 seconds are all optional. The native H3 film planner assigns compatible frames and event slots, not a hard 6-second project.
- **All modes and quality options remain available:** Chain5 / single-tail-frame / independent, 480p / 720p, ambient / native dialogue, all aspect ratios, screenplay review/edit, single-clip retakes, version selection, resume and assembly.
- For a low-memory smoke test **only if desired**, choose a 15-second film with 6-second clip ceiling and independent mode. This is not the default or a required workflow.
- 720p and 10/15-second shots may exhaust 12 GB VRAM, depending on offloading and current memory pressure; do not run MV and Film V2 on the GPU simultaneously.
- Retakes, preview, explicit take adoption, immutable final versions and resume retain their project files on F:.

## Audit boundaries

Port 8195 is reserved for this local application; MV 8193 and Film V2 Colab 8194 are unchanged. The API health response includes both runtime variant "rtx5070-fdrive" and resolved data_root; the launcher refuses a mismatched server. No model weights are copied or downloaded (only a small official camera prompt guide may be fetched if not already available).

Existing Python/V2 offline tests apply; Windows Powershell, live 5070 CUDA13 GPU generation and actual sound quality still require verification on the user machine. Do not merge to main before real-world tests.
