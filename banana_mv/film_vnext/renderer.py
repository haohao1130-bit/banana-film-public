"""H3 render handoff for a sealed whole-film VNext plan.

No language-model integration here. The injected renderer receives only final
H3 prompts and a clip index. Rendered clip paths are persisted after each
successful call for safe resume.
"""
import json
from pathlib import Path

from .pipeline import ProductionError, _atomic_text, load_ready


def render_ready(project_dir, render_clip):
    """Render strictly from sealed prompts, with durable per-clip resume.

    render_clip(index, prompt, clip_info) must return an existing finished video
    file path, or raise. No screenplay or camera model is called at render time.
    """
    root = Path(project_dir)
    manifest, prompts = load_ready(root)
    script = json.loads((root / "screenplay.json").read_text(encoding="utf-8"))
    if len(script["clips"]) != len(prompts):
        raise ProductionError("Script/manifest clip count mismatch")
    progress_path = root / "render_progress.json"
    if progress_path.exists():
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
        if progress.get("version") != manifest["version"] or progress.get("clip_count") != len(prompts):
            raise ProductionError("Render progress does not match sealed production")
    else:
        progress = {"version": manifest["version"],
                    "clip_count": len(prompts), "completed": {}}
    for index, (prompt, clip) in enumerate(zip(prompts, script["clips"])):
        key = str(index)
        old = progress["completed"].get(key)
        if old and Path(old).is_file():
            continue
        result = Path(render_clip(index, prompt, clip))
        if not result.is_file():
            raise ProductionError(f"Clip {index} renderer did not produce a video")
        progress["completed"][key] = str(result.resolve())
        _atomic_text(progress_path, json.dumps(progress, ensure_ascii=False, indent=2))
    return [Path(progress["completed"][str(i)]) for i in range(len(prompts))]
