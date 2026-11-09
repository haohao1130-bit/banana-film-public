"""Standalone HTTP service for Film VNext.

Only low-level H3 modules are reused. No legacy film director or writer routes.
All UI calls are same-origin; workspace paths are derived from server IDs.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import threading
import time
import uuid
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from PIL import Image

from banana_mv import services
from banana_mv.http_server import WebHandler
from banana_mv.film_vnext.pipeline import _atomic_text, load_ready
from banana_mv.film_vnext.local_adapter import prepare_local, run_h3

ROOT = Path(os.environ.get("BANANA_VNEXT_DATA", "/content/banana_film_vnext_data")).resolve()
WEB = Path(__file__).resolve().parent / "web"
ID_RE = re.compile(r"^[a-f0-9]{12}$")
ACTIVE_LOCK = threading.Lock()
ACTIVE = set()
GPU_LOCK = threading.Lock()
LAST_ERROR = 1800


def project(pid):
    if not isinstance(pid, str) or not ID_RE.fullmatch(pid):
        raise ValueError("無效的專案識別碼。")
    path = ROOT / "projects" / pid
    if not path.is_dir():
        raise FileNotFoundError("找不到專案。")
    return path


def read_state(folder):
    return json.loads((folder / "state.json").read_text(encoding="utf-8"))


def state(folder, **updates):
    with ACTIVE_LOCK:
        info = read_state(folder)
        info.update(updates, updated_at=time.time())
        _atomic_text(folder / "state.json", json.dumps(info, ensure_ascii=False, indent=2))
        return info


def snapshot(folder, include_prompts=False):
    info = read_state(folder)
    if (folder / "ready.json").exists():
        try:
            ready, prompts = load_ready(folder)
            info["ready"] = ready
            if include_prompts:
                script = json.loads((folder / "screenplay.json").read_text(encoding="utf-8"))
                info["screenplay"] = script
                info["prompts"] = prompts
        except Exception as exc:
            info["integrity_error"] = str(exc)
    progress_file = folder / "render_progress.json"
    if progress_file.is_file():
        try:
            prog = json.loads(progress_file.read_text(encoding="utf-8"))
            info["completed_clips"] = sorted(int(x) for x in prog.get("completed", {}))
        except (ValueError, TypeError):
            info["completed_clips"] = []
    info["has_film"] = (folder / "final.mp4").is_file()
    info["picture_slots"] = sorted(int(p.stem.split("_")[-1])
                                   for p in folder.glob("reference_*.*")
                                   if p.stem.split("_")[-1].isdigit())
    info["has_raw_screenplay"] = (folder / "screenplay_9b_raw.txt").exists()
    return info


def images(folder):
    paths = []
    for number in range(1, 10):
        choices = sorted(folder.glob(f"reference_{number:02d}.*"))
        if choices:
            if len(choices) != 1:
                raise ValueError("重複的圖片格號。")
            paths.append(choices[0])
        elif any(folder.glob(f"reference_{j:02d}.*") for j in range(number + 1, 10)):
            raise ValueError("參考圖格號需連續，請依 1、2、3… 上傳。")
    return paths


def spawn(pid, kind, fn):
    folder = project(pid)
    with ACTIVE_LOCK:
        if pid in ACTIVE:
            raise ValueError("專案正在處理中，請勿重複啟動。")
        ACTIVE.add(pid)
    def worker():
        try:
            # The single GPU/ComfyUI process must not receive concurrent model calls.
            with GPU_LOCK:
                state(folder, status=kind, error=None)
                fn(folder)
        except Exception as exc:
            state(folder, status="error", error=str(exc)[:LAST_ERROR])
        finally:
            with ACTIVE_LOCK:
                ACTIVE.discard(pid)
    thread = threading.Thread(target=worker, name=f"vnext-{kind}-{pid}", daemon=True)
    thread.start()


def prepare(folder):
    info = read_state(folder)
    if (folder / "ready.json").exists():
        load_ready(folder)
        state(folder, status="ready")
        return
    story = (folder / "story.txt").read_text(encoding="utf-8")
    picture_paths = images(folder)
    state(folder, step="9B 全片劇本 → 全片攝影 → H3 提示詞封存")
    cfg = services.load_config()
    prepare_local(cfg, folder, story, picture_paths,
                  max_seconds=info["max_seconds"], genre=info["genre"])
    state(folder, status="ready", step="全片備稿完成，等待確認開拍")


def render(folder):
    load_ready(folder)
    state(folder, step="H3 正在依封存稿拍攝，已完成片段可續拍")
    cfg = services.load_config()
    settings = read_state(folder)
    movie = run_h3(cfg, folder, images(folder),
                   size=(settings["width"], settings["height"]),
                   seed=settings["seed"], chain5=settings["chain5"])
    if not Path(movie).is_file():
        raise RuntimeError("沒有產出成片。")
    state(folder, status="done", step="拍攝與合成完成")


class Handler(WebHandler):
    def _query(self):
        return parse_qs(urlsplit(self.path).query)

    def _pid(self):
        return self._query().get("id", [None])[0]

    def reply_error(self, exc):
        code = 404 if isinstance(exc, FileNotFoundError) else 400
        self.send_json({"error": str(exc)[:LAST_ERROR]}, code)

    def do_GET(self):
        path = urlsplit(self.path).path
        try:
            if path in ("/", "/index.html"):
                return self.send_file(WEB / "vnext.html")
            if path in ("/vnext.js", "/vnext.css"):
                return self.send_file(WEB / path.lstrip("/"))
            if path == "/api/health":
                return self.send_json({"service": "banana-film-vnext", "version": 1})
            if path == "/api/projects":
                ROOT.joinpath("projects").mkdir(parents=True, exist_ok=True)
                entries = []
                for item in sorted((ROOT / "projects").iterdir(), reverse=True):
                    if ID_RE.fullmatch(item.name) and (item / "state.json").is_file():
                        entries.append(snapshot(item))
                return self.send_json({"projects": entries[:50]})
            if path in ("/api/project", "/api/plan"):
                return self.send_json(snapshot(project(self._pid()), path == "/api/plan"))
            if path == "/api/image":
                folder = project(self._pid())
                number = int(self._query().get("slot", [0])[0])
                if not 1 <= number <= 9:
                    raise ValueError("無效的圖片格號。")
                choices = list(folder.glob(f"reference_{number:02d}.*"))
                if not choices:
                    raise FileNotFoundError("沒有此參考圖。")
                return self.send_file(choices[0])
            if path == "/api/film":
                return self.send_file(project(self._pid()) / "final.mp4")
            if path == "/api/clip":
                index = int(self._query().get("index", [-1])[0])
                folder = project(self._pid())
                ready, _ = load_ready(folder)
                if not 0 <= index < ready["clip_count"]:
                    raise ValueError("片段不存在。")
                return self.send_file(folder / "parts" / f"{index:02d}.mp4")
            if path == "/api/diagnostic":
                folder = project(self._pid())
                raw = folder / "screenplay_9b_raw.txt"
                if not raw.is_file():
                    raise FileNotFoundError("目前沒有 9B 原始輸出。")
                # Bound error diagnostics; never emit arbitrary local path.
                return self.send_json({"text": raw.read_text(encoding="utf-8")[:12000]})
            return self.send_error(404)
        except Exception as exc:
            return self.reply_error(exc)

    def do_POST(self):
        path = urlsplit(self.path).path
        try:
            if path == "/api/create":
                body = self.body_json()
                story = body.get("story")
                if not isinstance(story, str) or not 1 <= len(story.strip()) <= 30000:
                    raise ValueError("請輸入 1–30000 字的故事提示詞。")
                max_seconds = body.get("max_seconds", 30)
                if type(max_seconds) not in (int, float) or not 6 <= max_seconds <= 180:
                    raise ValueError("全片時間上限為 6–180 秒。")
                width, height = body.get("width", 720), body.get("height", 1280)
                if (width, height) not in ((720, 1280), (1280, 720)):
                    raise ValueError("目前支援 9:16 或 16:9 的 720p 生成。")
                seed = body.get("seed", 17)
                if type(seed) is not int or not 0 <= seed <= 2**48-1:
                    raise ValueError("Seed 必須是合法非負整數。")
                name = str(body.get("name") or "未命名電影").strip()[:100]
                genre = str(body.get("genre") or "真人電影").strip()[:180]
                pid = uuid.uuid4().hex[:12]
                folder = ROOT / "projects" / pid
                folder.mkdir(parents=True, exist_ok=False)
                _atomic_text(folder / "story.txt", story.strip())
                info = {"id": pid, "name": name, "status": "draft", "step": "等待角色圖片與備稿",
                        "max_seconds": max_seconds, "genre": genre, "width": width,
                        "height": height, "seed": seed, "chain5": body.get("chain5") is True,
                        "created_at": time.time(), "updated_at": time.time(), "error": None}
                _atomic_text(folder / "state.json", json.dumps(info, ensure_ascii=False, indent=2))
                return self.send_json(info, 201)
            if path == "/api/upload":
                folder = project(self._pid())
                if read_state(folder)["status"] != "draft":
                    raise ValueError("備稿後不得更換圖片；請建立新專案版本。")
                slot = int(self._query().get("slot", [0])[0])
                if not 1 <= slot <= 9:
                    raise ValueError("圖片格號為 1–9。")
                from io import BytesIO
                body = self.read_body(12 * 1024 * 1024)
                with Image.open(BytesIO(body)) as pic:
                    pic.verify()
                with Image.open(BytesIO(body)) as pic:
                    fmt = pic.format
                ext = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}.get(fmt)
                if not ext:
                    raise ValueError("請使用 JPG、PNG 或 WEBP。")
                for prior in folder.glob(f"reference_{slot:02d}.*"):
                    prior.unlink()
                target = folder / f"reference_{slot:02d}{ext}"
                target.write_bytes(body)
                return self.send_json({"slot": slot, "bytes": len(body)}, 201)
            if path == "/api/prepare":
                folder = project(self._pid())
                if read_state(folder)["status"] not in ("draft", "error", "interrupted"):
                    raise ValueError("此專案不能再次備稿。")
                if (folder / "ready.json").is_file():
                    raise ValueError("此專案已封存拍攝稿，請按開拍。")
                images(folder)
                spawn(folder.name, "preparing", prepare)
                return self.send_json({"id": folder.name, "status": "preparing"}, 202)
            if path == "/api/render":
                folder = project(self._pid())
                load_ready(folder)
                if read_state(folder)["status"] not in ("ready", "error", "interrupted", "done"):
                    raise ValueError("請先完成並檢查全片備稿。")
                spawn(folder.name, "rendering", render)
                return self.send_json({"id": folder.name, "status": "rendering"}, 202)
            return self.send_error(404)
        except Exception as exc:
            return self.reply_error(exc)


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "projects").mkdir(exist_ok=True)
    for folder in (ROOT / "projects").iterdir():
        if ID_RE.fullmatch(folder.name) and (folder / "state.json").exists():
            info = read_state(folder)
            if info["status"] in ("preparing", "rendering"):
                state(folder, status="interrupted", error="執行階段已重啟；完成影片保留，可繼續拍攝。")
    port = int(os.environ.get("BANANA_VNEXT_PORT", "8192"))
    print(f"Banana VNext UI http://127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
