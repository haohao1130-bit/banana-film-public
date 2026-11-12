"""BANANA FILM V2 end-to-end controller.

Deliberately does NOT import the legacy banana_mv.film plan/worker or its take
director. Reuses only tested Comfy transport, native AV codec, H3 graph,
five-frame image guidance, asset storage and immutable master archive.
"""
from __future__ import annotations
import copy
import json
import math
from pathlib import Path
import random
import re
import shutil
import threading
import time
import uuid

from banana_mv import server as app, masters
from banana_mv import services as backend
from banana_mv.core import dimensions, output_dimensions
from banana_mv.film_continuity import (motion_prefix, prepare_motion_tail,
                                       add_motion_guide, preflight_nodes)
from banana_mv.film_media import require_audio, trim_native
from banana_mv.scene_state import atomic_json
from .directors import screenplay as write_screenplay, camera as write_camera, source_to_picture
from .production import compile_film, FilmPlanError

ENGINE = "python_owned_film_v2"
TERMINAL = frozenset(("done", "error", "cancelled", "interrupted", "script_ready"))
INTENSITIES = ("normal", "high", "extreme")
STYLES = ("真人電影", "動畫", "特攝", "依故事決定")


def _job(job_id):
    obj = app.read_state(job_id)
    if obj.get("engine") != ENGINE:
        raise ValueError("不是本版 Python-Owned 短片專案。")
    return obj


def _save(job):
    app.write_state(job)


def _work(job):
    return app.job_dir(job["id"])


def _version_part(job, index, version=None):
    seg = job["segments"][index]
    version = seg.get("selected_version", 1) if version is None else version
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValueError("毛片版本編號錯誤。")
    if version != 1 and not any(x["version"] == version and x["status"] == "ready"
                               for x in seg.get("takes", [])):
        raise ValueError("毛片版本尚未製作完成。")
    path = _work(job) / f"{index:02d}_part_v{version}.mp4"
    if not path.is_file():
        raise ValueError("毛片檔案遺失，不能採用。")
    return path


def _originals(job, cfg):
    sources = [backend.safe_child(_work(job), p) for p in job["sources"]["images"]]
    if len(sources) != len(job["images_comfy"]) or any(not p.is_file() for p in sources):
        raise ValueError("參考圖片來源遺失或數量不符。")
    inp = Path(cfg["comfy_input_dir"])
    inp.mkdir(parents=True, exist_ok=True)
    for source, name in zip(sources, job["images_comfy"]):
        shutil.copyfile(source, backend.safe_child(inp, name))
    return sources


def _request(raw):
    if not isinstance(raw, dict):
        raise ValueError("生成設定必須是物件。")
    req = dict(raw)
    text = req.get("prompt")
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 30000:
        raise ValueError("請填寫 1–30000 字的故事。")
    maximum = req.get("max_seconds", 30)
    if isinstance(maximum, bool) or not isinstance(maximum, (int, float)) or not math.isfinite(maximum) or not 6 <= maximum <= 180:
        raise ValueError("試拍長度必須在 6–180 秒。")
    chunk = req.get("segment_seconds", 15)
    if chunk == "auto":
        chunk = 15
    if isinstance(chunk, bool) or chunk not in (6, 10, 15):
        raise ValueError("單段上限請選 6、10 或 15 秒。")
    if req.get("mode", "chain5") not in ("independent", "chain", "chain5"):
        raise ValueError("未知接續模式。")
    slots = req.get("image_slots", [None] * 9)
    if not isinstance(slots, list) or len(slots) != 9 or any(
            x is not None and (not isinstance(x, str) or not x) for x in slots):
        raise ValueError("圖片必須使用九個固定位置，空格填 null。")
    count = sum(x is not None for x in slots)
    if count > (8 if req.get("mode") == "chain" else 9):
        raise ValueError("單張末幀模式最多八張圖片，其他模式最多九張。")
    source_to_picture(text, slots)
    if req.get("sound_mode", "ambient") not in ("ambient", "dialogue"):
        raise ValueError("聲音模式只能選環境音或依故事安排對白。")
    if req.get("visual_style", "真人電影") not in STYLES:
        raise ValueError("不支援的影片風格。")
    if req.get("intensity", "high") not in INTENSITIES:
        raise ValueError("不支援的攝影強度。")
    if any(not isinstance(req.get(k, default), bool) for k, default in
           (("auto_director", True), ("script_review", True),
            ("kitchen_attention", True), ("sparse_attention", False),
            ("motion_lora", True))):
        raise ValueError("勾選值必須是布林值。")
    retries = req.get("rewrite_retries", 2)
    if isinstance(retries, bool) or not isinstance(retries, int) or not 0 <= retries <= 4:
        raise ValueError("9B 重試請設定 0–4 次。")
    seed = req.get("seed")
    if seed in (None, ""):
        seed = random.randrange(2**48)
    elif isinstance(seed, bool) or not str(seed).isdigit() or not 0 <= int(seed) < 2**48:
        raise ValueError("Seed 必須是 0–281474976710655 的整數。")
    req.update(production="film", film_engine=ENGINE, image_slots=slots,
               image_ids=[x for x in slots if x is not None],
               max_seconds=float(maximum), target_seconds=float(maximum),
               segment_seconds=float(chunk), target_min_seconds=min(10., float(chunk)),
               mode=req.get("mode", "chain5"), sound_mode=req.get("sound_mode", "ambient"),
               visual_style=req.get("visual_style", "真人電影"),
               intensity=req.get("intensity", "high"), auto_director=req.get("auto_director", True),
               script_review=req.get("script_review", True),
               rewrite_retries=retries, seed=int(seed), film_motion_version=2,
               sampling_steps=8, kitchen_attention=req.get("kitchen_attention", True),
               sparse_attention=req.get("sparse_attention", False),
               motion_lora=req.get("motion_lora", True))
    return req


def _verify_doc(doc, req):
    if not isinstance(doc, dict):
        raise FilmPlanError("審閱劇本必須是 JSON 物件。")
    if req["sound_mode"] == "ambient" and any(
            isinstance(b, dict) and b.get("dialogue") for b in doc.get("beats", [])):
        raise FilmPlanError("環境音模式不能包含對白。")
    return compile_film(doc, max_seconds=req["max_seconds"],
                        max_clip_seconds=req["segment_seconds"],
                        target_min_seconds=req["target_min_seconds"])


def _apply_plan(job, doc, plan):
    work = _work(job)
    old = job.get("screenplay")
    if old is not None:
        job.setdefault("script_history", []).append({"at": time.time(), "script": old})
    job["screenplay"] = copy.deepcopy(doc)
    job["script_draft"] = copy.deepcopy(doc)
    job["script_revision"] = uuid.uuid4().hex
    job["production_plan_sha256"] = plan["plan_sha256"]
    job["title"] = str(job["request"].get("project_name") or plan["title"])[:120]
    job["duration"] = plan["duration_seconds"]
    job["segments"] = []
    for clip in plan["clips"]:
        event_text = "\n".join(e["action"] for e in clip["events"])
        mode = "action" if re.search(r"拳|打|戰|攻|逃|追|爆炸|fight|chase", event_text, re.I) else "story"
        job["segments"].append({
            "index": clip["index"], "start": clip["start_seconds"], "seconds": clip["seconds"],
            "frames": clip["frames"], "start_frame": clip["start_frame"],
            "model_frames": clip["frames"], "director_mode": mode,
            "director_plan": {"index": clip["index"], "mode": mode, "event": event_text},
            "event_ids": clip["event_ids"], "boundary": clip["boundary"],
            "state_at_open": clip["state_at_open"], "state_at_close": clip["state_at_close"],
            "status": "waiting", "selected_version": 1, "takes": []
        })
    atomic_json(work / "v2_screenplay.json", doc)
    atomic_json(work / "v2_plan.json", plan)
    _save(job)


def start(raw):
    req = _request(raw)
    cfg = copy.deepcopy(backend.load_config())
    if not Path(cfg["guides"]["ref"]).is_file():
        raise ValueError("缺少 H3 官方攝影指南，請先執行 Notebook ②。")
    app.preflight(cfg, {"encoder": {"class_type": "CLIPLoader",
                                  "inputs": {"clip_name": cfg["rewriter"]["model"]}},
                        "generate": {"class_type": "TextGenerate", "inputs": {}}})
    if req["mode"] == "chain5":
        app.preflight(cfg, preflight_nodes())
    rows = [backend.asset(asset_id) for asset_id in req["image_ids"]]
    if any(item["kind"] != "image" for item in rows):
        raise ValueError("參考素材只接受圖片。")
    size = dimensions(req.get("aspect", "16:9"), req.get("width"))
    output = output_dimensions(req.get("aspect", "16:9"), req.get("width"))
    if not app.GPU_LOCK.acquire(blocking=False):
        raise ValueError("已有一部短片正在製作中。")
    try:
        queue = backend.comfy(cfg, "/queue")
        if queue.get("queue_running") or queue.get("queue_pending"):
            raise ValueError("ComfyUI 尚有工作，請等佇列清空。")
        job_id = uuid.uuid4().hex[:12]
        work = app.RUNS / job_id
        work.mkdir(parents=True)
        directory = work / "sources"
        directory.mkdir()
        image_paths = []
        for index, item in enumerate(rows):
            source = backend.LIBRARY / item["file"]
            dest = directory / f"image_{index}{source.suffix.lower()}"
            shutil.copyfile(source, dest)
            image_paths.append(str(dest.relative_to(work)))
        job = {
            "id": job_id, "engine": ENGINE, "request": req,
            "created": time.time(), "status": "planning_story", "seed": req["seed"],
            "title": str(req.get("project_name") or "Python 短片 V2")[:120],
            "duration": 0, "segments": [], "size": size, "output_size": output,
            "images_comfy": [item["comfy_name"] for item in rows],
            "sources": {"images": image_paths}, "settings_version": 3,
            "timeline_source": ENGINE, "visual_verified": False,
            "note": "Python owns event slots; generated H3 video/audio still needs human review."
        }
        _save(job)
        threading.Thread(target=_worker, args=(job, cfg), daemon=True).start()
        return public(job)
    except Exception:
        app.GPU_LOCK.release()
        raise


def _worker(job, cfg):
    try:
        originals = _originals(job, cfg)
        if not job.get("screenplay"):
            job["status"] = "planning_story"
            _save(job)
            doc, plan = write_screenplay(cfg, job["request"], originals, _work(job))
            _apply_plan(job, doc, plan)
        if job["request"]["script_review"] and not job.get("script_approved"):
            job["status"] = "script_ready"
            _save(job)
            return
        plan = json.loads((_work(job) / "v2_plan.json").read_text(encoding="utf-8"))
        for seg in job["segments"]:
            if job["id"] in app.CANCEL:
                job["status"] = "cancelled"
                _save(job)
                return
            index = seg["index"]
            job["current"] = index + 1
            selected = _work(job) / f"{index:02d}_part_v{seg.get('selected_version', 1)}.mp4"
            if seg["status"] == "done" and app.valid_part(selected, seg, job["size"]):
                require_audio(selected)
                continue
            _render_one(job, cfg, originals, plan, index, 1, None)
        if job["id"] in app.CANCEL:
            job["status"] = "cancelled"
            _save(job)
            return
        _assemble(job, "original" if not job.get("current_master") else "resume")
        job["status"] = "done"
        job.pop("error", None)
        job.pop("error_stage", None)
        job.pop("resuming", None)
        _save(job)
    except Exception as exc:
        job.update(error_stage=job.get("status"), status="error",
                   error=f"{type(exc).__name__}: {exc}")
        _save(job)
    finally:
        app.CANCEL.discard(job["id"])
        app.GPU_LOCK.release()


def _render_one(job, cfg, originals, plan, index, version, correction):
    seg = job["segments"][index]
    work = _work(job)
    inp = Path(cfg["comfy_input_dir"])
    temp = []
    prefix = motion_prefix(job, seg)
    guide = []
    first = None
    tail = None
    try:
        if index and job["request"]["mode"] == "chain":
            tail = work / f"{index:02d}_v{version}_opening.png"
            app.last_frame(_version_part(job, index - 1), tail)
            first = f"banana_v2_{job['id']}_{index}_v{version}_opening.png"
            shutil.copyfile(tail, inp / first)
            temp.append(inp / first)
        if prefix:
            names, receipt = prepare_motion_tail(
                _version_part(job, index - 1), work / "v2_motion_context", inp,
                f"v2_motion_{job['id']}_{index}_v{version}")
            guide = names
            temp.extend(inp / name for name in names)
            prior_receipt = seg.get("motion_context")
            if (version == 1 and prior_receipt and seg.get("prompt_id") and
                    prior_receipt.get("source_sha256") != receipt["source_sha256"]):
                raise ValueError("前段採用版本已變；不能沿用舊 Chain5 佇列。請改由補拍建立新候選。")
            seg["motion_context"] = receipt
        prompt_path = work / f"{index:02d}_prompt_v{version}.txt"
        if version == 1 and correction is None and prompt_path.is_file() and not seg.get("refresh_prompt"):
            prompt = prompt_path.read_text(encoding="utf-8")
        else:
            job["status"] = "retaking" if version > 1 else "running"
            seg["status"] = "rewriting" if version == 1 else seg["status"]
            _save(job)
            previous = (work / f"{index:02d}_prompt_v{seg.get('selected_version', 1)}.txt")
            prompt = write_camera(cfg, job["request"], plan, index, originals, work,
                                  tail=tail, correction=correction,
                                  base=previous.read_text(encoding="utf-8") if correction and previous.is_file() else None,
                                  version=version)
            prompt_path.write_text(prompt, encoding="utf-8")
        if version == 1:
            seg.update(prompt=prompt, status="generating")
            _save(job)
        frame_count = seg["frames"]
        seed = (job["seed"] + index + (version - 1) * 7907) % (2**48)
        graph = app.build_workflow(job["images_comfy"], None, *job["size"],
                                   frame_count, prompt, seed, first,
                                   **app.graph_options(job["request"], seg["seconds"], seg))
        if guide:
            add_motion_guide(graph, guide, frame_count)
        graph["16"]["inputs"]["filename_prefix"] = f"BananaFilmV2/{job['id']}/{index:02d}_v{version}"
        atomic_json(work / f"{index:02d}_workflow_v{version}.json", graph)
        app.preflight(cfg, graph)
        pid = None
        if version == 1 and seg.get("prompt_id") and job.get("resuming"):
            old = backend.history_entry(cfg, seg["prompt_id"])
            if old and old.get("status", {}).get("completed") and old.get("status", {}).get("status_str") != "error":
                entry = old
                pid = seg["prompt_id"]
            else:
                entry = None
        else:
            entry = None
        if entry is None:
            pid = backend.queue_prompt(cfg, graph)
            if version == 1:
                seg["prompt_id"] = pid
                _save(job)
            entry = app.wait_generation(cfg, pid, job)
        raw = work / f"{index:02d}_raw_v{version}.mp4"
        part = work / f"{index:02d}_part_v{version}.mp4"
        backend.comfy_download(cfg, app.video_info(entry), raw)
        trim_native(raw, part, frame_count, prefix_frames=prefix)
        if not app.valid_part(part, seg, job["size"]):
            raise ValueError("生成影片的影格或尺寸不符合已核定的 Python 槽位。")
        require_audio(part)
        if version == 1:
            seg.update(status="done", selected_version=1)
        else:
            seg.setdefault("takes", []).append({"version": version, "status": "ready",
                                                "seed": seed, "created": time.time()})
        _save(job)
        return part
    finally:
        for path in temp:
            path.unlink(missing_ok=True)


def _assemble(job, reason):
    work = _work(job)
    parts = [_version_part(job, index) for index in range(len(job["segments"]))]
    for part in parts:
        require_audio(part)
    job["status"] = "assembling"
    _save(job)
    masters.preserve_current(job, work)
    candidate = work / "final_pending.mp4"
    app.assemble(parts, None, candidate, job["duration"], job["output_size"])
    version = masters.archive(job, work, candidate, reason,
                              choices={i: "v" + str(seg.get("selected_version", 1))
                                       for i, seg in enumerate(job["segments"])})
    candidate.replace(work / "final.mp4")
    job["current_master"] = version["version"]
    job["video"] = f"/api/film-v2/file?id={job['id']}"
    try:
        app.export_finished_video(job, work / "final.mp4")
    except OSError as exc:
        job["export_error"] = str(exc)
    _save(job)


def _lock_idle(job):
    if job["status"] not in TERMINAL:
        raise ValueError("目前正在處理其他工作。")
    if not app.GPU_LOCK.acquire(blocking=False):
        raise ValueError("已有其他 H3／9B 任務在執行。")
    try:
        q = backend.comfy(backend.load_config(), "/queue")
        if q.get("queue_running") or q.get("queue_pending"):
            raise ValueError("ComfyUI 尚有工作。")
    except Exception:
        app.GPU_LOCK.release()
        raise


def approve(job_id, revision, draft=None):
    job = _job(job_id)
    if job["status"] != "script_ready" or revision != job.get("script_revision"):
        raise ValueError("劇本已更新或尚未進入確認階段，請重新載入。")
    doc = draft if draft is not None else job["screenplay"]
    plan = _verify_doc(doc, job["request"])
    _lock_idle(job)
    try:
        _apply_plan(job, doc, plan)
        job.update(status="running", script_approved=True, resumed=time.time())
        _save(job)
        cfg = copy.deepcopy(backend.load_config())
        threading.Thread(target=_worker, args=(job, cfg), daemon=True).start()
        return public(job)
    except Exception:
        app.GPU_LOCK.release()
        raise


def revise(job_id, revision, instruction, draft=None):
    job = _job(job_id)
    if job["status"] != "script_ready" or revision != job.get("script_revision"):
        raise ValueError("劇本已更新或不能修改，請重新載入。")
    if not isinstance(instruction, str) or not 1 <= len(instruction.strip()) <= 3000:
        raise ValueError("請提供 1–3000 字的修改意見。")
    current = draft if draft is not None else job["screenplay"]
    _verify_doc(current, job["request"])
    _lock_idle(job)
    try:
        job["status"] = "revising_story"
        _save(job)
        threading.Thread(target=_revise_worker,
                         args=(job, copy.deepcopy(backend.load_config()), current, instruction),
                         daemon=True).start()
        return public(job)
    except Exception:
        job["status"] = "script_ready"
        _save(job)
        app.GPU_LOCK.release()
        raise


def _revise_worker(job, cfg, current, instruction):
    try:
        originals = _originals(job, cfg)
        doc, plan = write_screenplay(cfg, job["request"], originals, _work(job),
                                     instruction=instruction, current=current)
        _apply_plan(job, doc, plan)
        job.pop("revision_error", None)
    except Exception as exc:
        # Preserve the entire last approved draft, never overwrite it on failure.
        job["revision_error"] = f"{type(exc).__name__}: {exc}"
    finally:
        job["status"] = "script_ready"
        _save(job)
        app.GPU_LOCK.release()


def resume(job_id):
    job = _job(job_id)
    if job["status"] not in ("error", "cancelled", "interrupted"):
        raise ValueError("此工作不能續跑，已核准劇本請先按確認開拍。")
    if not job.get("script_approved"):
        raise ValueError("劇本尚未核准，請建立新的試拍。")
    _lock_idle(job)
    try:
        job.update(status="running", resuming=True, resumed=time.time())
        job.pop("error", None)
        _save(job)
        threading.Thread(target=_worker, args=(job, copy.deepcopy(backend.load_config())), daemon=True).start()
        return public(job)
    except Exception:
        app.GPU_LOCK.release()
        raise


def retake(job_id, index, instruction=""):
    job = _job(job_id)
    if job["status"] != "done":
        raise ValueError("完整短片完成後才能補拍。")
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(job["segments"]):
        raise ValueError("補拍段落不存在。")
    if not isinstance(instruction, str) or len(instruction) > 3000:
        raise ValueError("補拍意見最多 3000 字。")
    _lock_idle(job)
    try:
        seg = job["segments"][index]
        next_version = max([1] + [t["version"] for t in seg.get("takes", [])]) + 1
        job["retake"] = {"index": index, "version": next_version, "status": "running"}
        job["status"] = "retaking"
        _save(job)
        threading.Thread(target=_retake_worker,
                         args=(job, copy.deepcopy(backend.load_config()), index,
                               next_version, instruction), daemon=True).start()
        return public(job)
    except Exception:
        app.GPU_LOCK.release()
        raise


def _retake_worker(job, cfg, index, version, instruction):
    try:
        originals = _originals(job, cfg)
        plan = json.loads((_work(job) / "v2_plan.json").read_text(encoding="utf-8"))
        _render_one(job, cfg, originals, plan, index, version, instruction or None)
        job["retake"]["status"] = "ready"
        job["status"] = "done"
    except Exception as exc:
        job["retake"].update(status="error", error=f"{type(exc).__name__}: {exc}")
        job["status"] = "done"
    finally:
        _save(job)
        app.GPU_LOCK.release()


def adopt(job_id, index, version):
    job = _job(job_id)
    if job["status"] != "done":
        raise ValueError("目前不能採用毛片。")
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(job["segments"]):
        raise ValueError("段落編號無效。")
    if isinstance(version, bool) or not isinstance(version, int):
        raise ValueError("版本編號必須是整數。")
    _version_part(job, index, version)
    _lock_idle(job)
    try:
        old = job["segments"][index].get("selected_version", 1)
        job["segments"][index]["selected_version"] = version
        try:
            _assemble(job, "adopted_retake")
        except Exception:
            job["segments"][index]["selected_version"] = old
            job["status"] = "done"
            _save(job)
            raise
        job["status"] = "done"
        job["continuity_warning"] = ("若改動前段、使用 Chain5／末幀接續，已完成後段不會偷偷重拍；"
                                     "請檢查接縫並視需要逐段補拍。")
        _save(job)
        return public(job)
    finally:
        app.GPU_LOCK.release()


def public(job):
    data = copy.deepcopy(job)
    work = _work(job)
    for seg in data.get("segments", []):
        index = seg["index"]
        if (work / f"{index:02d}_part_v{seg.get('selected_version', 1)}.mp4").is_file():
            seg["preview"] = f"/api/film-v2/clip?id={job['id']}&index={index}"
    for version in data.get("final_versions", []):
        version["download"] = f"/api/film-v2/file?id={job['id']}&version={version['version']}"
    return data


def projects():
    result = []
    for path in app.RUNS.glob("*/status.json"):
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
            if job.get("engine") == ENGINE:
                result.append({"id": job["id"], "title": job.get("title"),
                               "status": job["status"], "updated": job.get("resumed", job["created"]),
                               "completed": sum(x["status"] == "done" for x in job["segments"]),
                               "total": len(job["segments"])})
        except (ValueError, KeyError, OSError):
            continue
    return sorted(result, key=lambda x: x["updated"], reverse=True)


def get(job_id):
    return public(_job(job_id))


def clip(job_id, index, version=None):
    job = _job(job_id)
    if not 0 <= index < len(job["segments"]):
        raise ValueError("段落超出範圍。")
    return _version_part(job, index, version)


def file(job_id, version=None):
    job = _job(job_id)
    return masters.source(job, _work(job), version)


def stop(job_id):
    job = _job(job_id)
    if job["status"] not in ("running", "planning_story", "retaking", "revising_story"):
        raise ValueError("沒有正在生成的工作。")
    app.CANCEL.add(job_id)
    return {"ok": True, "message": "已要求目前段落完成後停止。"}
