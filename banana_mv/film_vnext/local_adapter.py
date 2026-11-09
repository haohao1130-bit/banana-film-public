"""Optional real ComfyUI/H3 adapter for the independent VNext pipeline.

This only reuses proven low-level H3 media primitives. It never calls legacy
film.py's director, writer or production worker.
"""
import json
from pathlib import Path
import shutil
import uuid

from banana_mv import server as app
from banana_mv.core import build_workflow
from banana_mv.film_continuity import prepare_motion_tail
from .motion import add_audio_t8_motion_guide
from banana_mv.film_media import trim_native, require_audio

from .pipeline import FilmVNext, ProductionError, load_ready
from .renderer import render_ready


class Local9B:
    """Bridge the two VNext whole-film requests to the installed local 9B."""
    def __init__(self, cfg, pictures=()):
        self.cfg = cfg
        self.pictures = list(pictures)

    def __call__(self, role, task):
        if role not in ("WHOLE_FILM_SCREENWRITER", "WHOLE_FILM_CAMERA_ONLY"):
            raise ProductionError("Unknown VNext model role")
        system = ("You are the SOLE full-film screenwriter, creating the entire "
                  "film screenplay once, as strict JSON. No camera planning. "
                  if role == "WHOLE_FILM_SCREENWRITER" else
                  "You are the full-film camera director. Strict camera-only JSON. "
                  "The screenplay is immutable. Never invent, delete, retime or "
                  "rewrite a story event.")
        # The screenplay writer may inspect connected character references.
        # The camera planner only needs the validated screenplay text.
        parts = [("text", json.dumps(task, ensure_ascii=False))]
        if role == "WHOLE_FILM_SCREENWRITER":
            from PIL import Image, ImageOps
            for index, path in enumerate(self.pictures, 1):
                with Image.open(path) as img:
                    copy = ImageOps.exif_transpose(img).convert("RGB")
                    copy.thumbnail((768, 768))
                    parts.extend([("text", f"<Picture {index}>:"), ("image", copy)])
        return app.backend.rewrite_local(self.cfg, system, parts, uuid.uuid4().hex[:8])


def prepare_local(cfg, project_dir, story, pictures=(), *, max_seconds=180, genre="cinematic"):
    """Runs only the two 9B planning calls; H3 is not touched."""
    return FilmVNext(Local9B(cfg, pictures)).prepare(
        project_dir, story, picture_count=len(pictures),
        max_seconds=max_seconds, genre=genre)


def run_h3(cfg, project_dir, picture_paths, *, size=(720, 1280),
           seed=17, chain5=True, graph_settings=None):
    """Render a fully prepared script via native H3 and resumable clip files.

    If chain5=True, reuse the previous rendered last five frames without
    passing them into a new LLM rewrite. Paths must be existing local pictures.
    """
    project_dir = Path(project_dir)
    manifest, _ = load_ready(project_dir)
    script = json.loads((project_dir / "screenplay.json").read_text(encoding="utf-8"))
    pictures = [Path(p) for p in picture_paths]
    # Some subjects may intentionally share one original image.
    used = [s["picture"] for s in script["subjects"] if s.get("picture") is not None]
    if not pictures:
        raise ProductionError('H3 Ref2VA 拍攝前至少需要一張角色／場景參考圖。')
    if used and max(used) > len(pictures):
        raise ProductionError("Missing original actor reference pictures")
    folder = Path(cfg["comfy_input_dir"])
    folder.mkdir(parents=True, exist_ok=True)
    inputs = []
    for i, source in enumerate(pictures, 1):
        if not source.is_file():
            raise ProductionError(f"Missing input reference {i}")
        name = f"film_vnext_{project_dir.name}_ref_{i:02d}{source.suffix.lower()}"
        shutil.copyfile(source, folder / name)
        inputs.append(name)
    options = dict(graph_settings or {})
    options.setdefault("native_audio", True)
    options.setdefault("steps", 8)
    options.setdefault("director_mode", "story")
    options.setdefault("intensity", "high")
    options.setdefault("acceleration", True)
    options.setdefault("kitchen_attention", True)
    options.setdefault("sparse_attention", True)
    options.setdefault("motion_lora", False)
    parts = project_dir / "parts"
    parts.mkdir(exist_ok=True)
    generated = []

    def produce(index, prompt, clip):
        frames = clip["render_frames"]
        graph = build_workflow(inputs, None, *size, frames, prompt,
                               (seed + index) % (2**48), None, **options)
        extra_names = []
        if chain5 and index > 0:
            prior = parts / f"{index-1:02d}.mp4"
            if not prior.exists():
                raise ProductionError("Missing previous rendered clip for chain5")
            extra_names, _ = prepare_motion_tail(
                prior, project_dir / "motion_tail", folder,
                f"film_vnext_{project_dir.name}_{index:02d}")
            add_audio_t8_motion_guide(graph, extra_names, frames)
        graph["16"]["inputs"]["filename_prefix"] = (
            f"BananaFilmVNext/{project_dir.name}/{index:02d}")
        app.preflight(cfg, graph)
        prompt_id = app.backend.queue_prompt(cfg, graph)
        try:
            entry = app.wait_generation(cfg, prompt_id, {"id": project_dir.name})
            raw = project_dir / f"{index:02d}_raw.mp4"
            app.backend.comfy_download(cfg, app.video_info(entry), raw)
            out = parts / f"{index:02d}.mp4"
            trim_native(raw, out, frames, prefix_frames=5 if extra_names else 0)
            require_audio(out)
            generated.append(index)
            return out
        finally:
            for name in extra_names:
                (folder / name).unlink(missing_ok=True)

    clips = render_ready(project_dir, produce)
    # Pure media assembly; no further screenplay or camera model invocation.
    from banana_mv.core import assemble
    pending = project_dir / "final_pending.mp4"
    assemble(clips, None, pending, manifest["duration_ms"] / 1000, size)
    pending.replace(project_dir / "final.mp4")
    return project_dir / "final.mp4"
