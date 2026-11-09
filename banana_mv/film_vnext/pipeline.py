"""Independent whole-film-first production pipeline.

No imports from legacy film.py and no per-render LLM calls. The only LLM
boundaries are write_screenplay() and design_cameras(), both *before* render.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile

from banana_mv.direction_contract import validate_h3_sections

CAMERA_FIELDS = {
    "size": ("wide", "full", "medium", "close", "extreme_close", "over_shoulder", "detail"),
    "angle": ("eye", "low", "high", "side", "rear", "front", "overhead"),
    "motion": ("static", "track", "push", "pull", "pan", "tilt", "handheld", "arc", "follow"),
    "framing": ("balanced", "left", "right", "foreground", "headroom"),
    "lighting": ("natural", "side", "back", "soft", "contrast"),
}
CAMERA_DEFAULTS = {
    "size": "medium", "angle": "eye", "motion": "follow",
    "framing": "headroom", "lighting": "natural",
}
MAX_CLIPS = 34
MAX_DURATION_MS = 180000
HEADERS = ("subject_definitions", "summary", "retention_analysis",
           "detailed_description", "overall_soundscape", "non_diegetic_music")


class ProductionError(ValueError):
    """Invalid preproduction inputs; GPU work has not begun."""


def _json(raw):
    """Decode one intact JSON object, permitting a fenced model response.

    Never invent missing keys, close incomplete arrays, or rewrite a beat.
    Missing/malformed JSON stops preproduction before H3.
    """
    if isinstance(raw, str):
        candidate = raw.strip()
        if "</think>" in candidate:
            candidate = candidate.rsplit("</think>", 1)[-1].strip()
        if candidate.startswith("```"):
            lines = candidate.splitlines()
            if lines and re.fullmatch(r"```(?:json)?", lines[0].strip(), re.I):
                lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines.pop()
                candidate = "\n".join(lines).strip()
        try:
            parsed = json.loads(candidate)
            if not isinstance(parsed, dict):
                raise ProductionError("9B response must be a JSON object")
            return parsed
        except json.JSONDecodeError as exc:
            message = "9B did not return complete JSON"
            if not candidate:
                message = "9B returned empty text"
            elif not candidate.rstrip().endswith("}"):
                message = "9B JSON appears truncated or has trailing text"
            raise ProductionError(message + "; no H3 jobs queued") from exc
    if isinstance(raw, dict):
        return raw
    raise ProductionError("Expected JSON object")


def validate_script(raw, *, picture_count, max_seconds=180):
    """Validate structural integrity; NEVER invent or semantically rewrite beats."""
    data = _json(raw)
    if set(("title", "subjects", "clips")) - set(data):
        raise ProductionError("Script must contain title, subjects and clips")
    title, subjects, clips = data["title"], data["subjects"], data["clips"]
    if not isinstance(title, str) or not title.strip() or not isinstance(subjects, list):
        raise ProductionError("Invalid film title or subjects")
    if not isinstance(clips, list) or not 1 <= len(clips) <= MAX_CLIPS:
        raise ProductionError("Film needs 1–34 production clips")
    if not isinstance(picture_count, int) or isinstance(picture_count, bool) or not 0 <= picture_count <= 9:
        raise ProductionError("picture_count must be 0–9")
    # Accept a complete 1-based clip numbering convention by translating only\n    # positional metadata, never rewriting events or changing plot timing.\n    indices = [c.get("index") if isinstance(c, dict) else None for c in clips]\n    if indices == list(range(1, len(clips) + 1)):\n        data = json.loads(json.dumps(data, ensure_ascii=False))\n        clips = data["clips"]\n        for i, c in enumerate(clips):\n            c["index"] = i\n    ids, voices = set(), set()
    for subject in subjects:
        if not isinstance(subject, dict) or not isinstance(subject.get("id"), int) or isinstance(subject.get("id"), bool):
            raise ProductionError("Invalid subject ID")
        sid = subject["id"]
        if sid <= 0 or sid in ids:
            raise ProductionError("Duplicate subject ID")
        ids.add(sid)
        if not isinstance(subject.get("name"), str) or not subject["name"].strip():
            raise ProductionError("Missing named subject")
        pic = subject.get("picture")
        if pic is not None and (type(pic) is not int or not 1 <= pic <= picture_count):
            raise ProductionError("Unconnected picture reference")
        voice = subject.get("voice")
        if voice is not None:
            if type(voice) is not int or voice < 1 or voice in voices:
                raise ProductionError("Invalid or duplicate voice binding")
            voices.add(voice)
    total = 0
    seen = set()
    for index, clip in enumerate(clips):
        if not isinstance(clip, dict) or clip.get("index") != index or type(clip.get("duration_ms")) is not int:
            raise ProductionError(f"Clip {index+1}: index must be sequential (0-based or complete 1-based), duration_ms must be integer")
        duration = clip["duration_ms"]
        if not 5200 <= duration <= 15000:
            raise ProductionError("H3 clip duration must be between 5.2 and 15 seconds")
        beats = clip.get("beats")
        if not isinstance(beats, list) or not beats:
            raise ProductionError("Clip must contain screenplay beats")
        prev = -1
        for beat in beats:
            if not isinstance(beat, dict):
                raise ProductionError("Invalid beat")
            bid, start = beat.get("id"), beat.get("at_ms")
            if not isinstance(bid, str) or not bid or bid in seen:
                raise ProductionError("Every beat needs a globally unique ID")
            if type(start) is not int or start <= prev or start >= duration:
                raise ProductionError(f"Clip {index+1}, beat {bid}: at_ms={start} must be strictly increasing and below duration_ms={duration}")
            if not isinstance(beat.get("action"), str) or not beat["action"].strip():
                raise ProductionError("Each beat requires authoritative action text")
            if "<Audio " in beat["action"] or "<Video " in beat["action"]:
                raise ProductionError("No external source media in short film")
            speaker = beat.get("speaker")
            dialogue = beat.get("dialogue")
            if (speaker is None) != (dialogue is None):
                raise ProductionError("Dialogue and speaker must be paired")
            if speaker is not None:
                if type(speaker) is not int or speaker not in ids or not isinstance(dialogue, str) or not dialogue.strip():
                    raise ProductionError("Unbound dialogue")
            seen.add(bid)
            prev = start
        for field in ("opening_state", "outgoing_state"):
            if not isinstance(clip.get(field), str) or not clip[field].strip():
                raise ProductionError("Every clip requires explicit opening and outgoing state")
        total += duration
    ceiling = min(MAX_DURATION_MS, int(max_seconds * 1000))
    if total > ceiling:
        raise ProductionError(f"Film totals {total/1000:g}s, exceeding requested maximum {ceiling/1000:g}s")
    return data


def script_task(story, *, picture_count=0, max_seconds=180, genre="cinematic"):
    """One entire-script call; 180s is a ceiling, not a target to fill."""
    return {
        "role": "sole_screenwriter",
        "story": story, "genre": genre,
        "picture_count": picture_count, "hard_ceiling_seconds": max_seconds,
        "instructions": (
            "Write ONE complete causal film narrative. Return JSON only with title, "
            "subjects=[{id:int,name:str,picture:int|null,appearance:str,voice:int|null}], "
            "clips=[{index:int,duration_ms:int,opening_state:str,outgoing_state:str,"
            "beats:[{id:str,at_ms:int,action:str,speaker:int|null,dialogue:str|null}]}]. "
             "Clip index must start at 0 and increment by 1 (0,1,2...), "             "every beat id is globally unique, every clip duration 5200–15000 ms, "
             "Every beat at_ms must satisfy 0 <= at_ms < its clip duration_ms, "             "even the final beat; ending exactly at duration_ms is INVALID. "             "Beat times are local and strictly increasing. Story duration is naturally "
             "chosen, never padded to the limit; total duration MUST NOT exceed "             "hard_ceiling_seconds. Preserve user-required plot, names, "
            "cause-and-effect and the single intended ending. Intermediate outgoing "
            "states do not need a stop, pose or scene conclusion. Complete all clips "
            "in one response; no ellipsis, omitted sections or continuation requests."
        )
    }


def camera_task(script):
    """One full-movie camera call, with NO writable narrative attributes."""
    return {
        "role": "whole_film_cinematographer",
        "script": script,
        "instructions": (
            "Return JSON only: {clips:[{index:int,shots:[{at_ms:int,size:str,"
            "angle:str,motion:str,framing:str,lighting:str}]}]}. "
            "One clip entry for EVERY script clip, exact index order, first shot "
            "at 0, subsequent local times strictly increasing. Select creative "
            "shot sizes, perspectives, timing and movement across the whole film. "
            "NO event, story, summary, subject, action, dialogue, outcome, "
            "ending, description or other prose output fields. Those are wholly "
            "owned by the already-final screenplay. Allowed enum values: " +
            "; ".join(key + "=" + ",".join(values)
                      for key, values in CAMERA_FIELDS.items())
        )
    }


def _safe_camera(row, duration):
    if not isinstance(row, dict) or set(row) != {"index", "shots"}:
        return None
    shots = row["shots"]
    if not isinstance(shots, list) or not 1 <= len(shots) <= 32:
        return None
    previous = -1
    for shot in shots:
        if not isinstance(shot, dict) or set(shot) != set(CAMERA_FIELDS) | {"at_ms"}:
            return None
        timestamp = shot["at_ms"]
        if type(timestamp) is not int or timestamp <= previous or timestamp >= duration:
            return None
        for key, allowed in CAMERA_FIELDS.items():
            if shot[key] not in allowed:
                return None
        previous = timestamp
    return shots if shots[0]["at_ms"] == 0 else None


def validate_cameras(raw, script):
    """An incomplete response cannot partially overwrite a script.

    A deterministic photographic fallback is allowed; no narrative fallback
    is ever authored by the camera model or this validator.
    """
    try:
        data = _json(raw)
        rows = data["clips"]
        if not isinstance(rows, list) or len(rows) != len(script["clips"]):
            raise ProductionError("Incomplete whole-film camera plan")
        result = []
        for index, (row, clip) in enumerate(zip(rows, script["clips"])):
            if type(row.get("index")) is not int or row["index"] != index:
                raise ProductionError("Camera clip index mismatch")
            shots = _safe_camera(row, clip["duration_ms"])
            if shots is None:
                raise ProductionError("Invalid camera shot")
            result.append(shots)
        return result, False
    except (ProductionError, TypeError, KeyError, AttributeError):
        # No GPU is consumed by malformed 9B JSON. This fail-soft path keeps
        # every upstream beat and gives two distinct motivated framings.
        fallback = []
        for clip in script["clips"]:
            shots = [dict(CAMERA_DEFAULTS, at_ms=0)]
            if clip["duration_ms"] >= 8000 and len(clip["beats"]) > 1:
                pivot = clip["beats"][len(clip["beats"]) // 2]["at_ms"]
                if pivot > 0:
                    shots.append(dict(CAMERA_DEFAULTS, at_ms=pivot,
                                      size="close", angle="side", motion="track"))
            fallback.append(shots)
        return fallback, True


def _clock(ms):
    return f"{ms // 60000:02d}:{(ms // 1000) % 60:02d}.{ms % 1000:03d}"


def compile_clip(script, index, camera_shots):
    """The model cannot insert a narrative clause: all actions come from beats."""
    clip = script["clips"][index]
    duration = clip["duration_ms"]
    if _safe_camera({"index": index, "shots": camera_shots}, duration) is None:
        raise ProductionError("Cannot compile invalid camera timings")
    vocal_subjects = {b["speaker"] for b in clip["beats"] if b.get("speaker") is not None}
    definitions = []
    for subject in script["subjects"]:
        ident = f'<Subject {subject["id"]}>'
        if subject["id"] in vocal_subjects:
            if subject.get("voice") is None:
                raise ProductionError("Missing upstream voice ID for dialogue")
            ident += f' (S{subject["voice"]})'
        ident += f' {subject["name"]}'
        if subject.get("picture") is not None:
            ident += f' references <Picture {subject["picture"]}>'
        if subject.get("appearance"):
            ident += f'; {subject["appearance"]}'
        definitions.append(ident)
    if not definitions:
        definitions = ["Only subjects specified in the authoritative film script."]
    details = []
    for i, shot in enumerate(camera_shots):
        begin = shot["at_ms"]
        end = camera_shots[i+1]["at_ms"] if i+1 < len(camera_shots) else duration
        camera = ", ".join(f"{k}: {shot[k]}" for k in CAMERA_FIELDS)
        staged = []
        for beat in clip["beats"]:
            if begin <= beat["at_ms"] < end:
                cue = f'At local +{beat["at_ms"] - begin}ms: '
                action = beat["action"]
                if beat.get("speaker") is not None:
                    voice = next(s["voice"] for s in script["subjects"]
                                 if s["id"] == beat["speaker"])
                    action += f' <Subject {beat["speaker"]}> (S{voice}) <d>[Chinese] {beat["dialogue"]}</d>'
                staged.append(cue + action)
        if not staged:
            staged = ["Hold current commissioned action/attention without a new event."]
        prefix = f"[Shot {i+1}] " if i == 0 else f"[Shot {i+1}] At {_clock(begin)}, "
        details.append(prefix + camera + ". " + " ".join(staged))
    has_dialogue = bool(vocal_subjects)
    result = "\n\n".join((
        "subject_definitions:\n" + "\n".join(definitions),
        "summary:\n" + clip["opening_state"] + " " +
            " ".join(b["action"] for b in clip["beats"]) + " " + clip["outgoing_state"],
        "retention_analysis:\nPreserve commissioned cast identities, active scene state and connected pictures; "
            "visual references do not lock expressions or force cast attendance.",
        "detailed_description:\n" + "\n".join(details),
        "overall_soundscape:\n" + ("Only commissioned dialogue and natural scene effects." if has_dialogue
                                    else "Natural scene effects; no dialogue or singing."),
        "non_diegetic_music:\nN/A",
    ))
    validate_h3_sections(result)
    native_shots = re.findall(r"\[Shot (\d+)\]", result)
    if native_shots != [str(i + 1) for i in range(len(camera_shots))]:
        raise ProductionError("Native H3 shot numbering corrupted")
    speakers = re.findall(r"\(S(\d+)\)", result)
    if has_dialogue and not speakers:
        raise ProductionError("Missing commissioned speaker bindings")
    if not has_dialogue and speakers:
        raise ProductionError("Silent short film has invalid speaker markers")
    return result


def _atomic_text(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                     prefix=".vnext-", delete=False) as file:
        file.write(content)
        staged = Path(file.name)
    os.replace(staged, path)


class FilmVNext:
    """Self-contained preproduction engine: two LLM calls, zero during filming.

    rewrite(system, payload) is injected. Rendering is separately delegated to
    the future H3 adapter and is intentionally not invoked in prepare().
    """
    VERSION = 1

    def __init__(self, rewrite):
        self.rewrite = rewrite

    def prepare(self, project_dir, story, *, picture_count=0, max_seconds=180,
                genre="cinematic"):
        root = Path(project_dir)
        if (root / "ready.json").exists():
            raise ProductionError("Existing ready manifest is immutable; create a new version")
        if not isinstance(story, str) or not story.strip():
            raise ProductionError("Story required")
        if not (6 <= max_seconds <= 180):
            raise ProductionError("Duration ceiling must be 6–180s")
        screenplay_input = script_task(story, picture_count=picture_count,
                                       max_seconds=max_seconds, genre=genre)
        raw_screenplay = self.rewrite("WHOLE_FILM_SCREENWRITER", screenplay_input)
        # Preserve the untouched 9B output for debugging model JSON failures.
        # This is not a retry and does not start H3.
        root.mkdir(parents=True, exist_ok=True)
        _atomic_text(root / "screenplay_9b_raw.txt",
                     raw_screenplay if isinstance(raw_screenplay, str)
                     else json.dumps(raw_screenplay, ensure_ascii=False))
        try:
            screenplay = validate_script(raw_screenplay,
                                         picture_count=picture_count, max_seconds=max_seconds)
        except ProductionError as first_error:
            # Retry a failed *whole-film* draft once using the explicit schema
            # violation. Never patch beat times, omit actions, or send H3.
            repair_input = dict(screenplay_input)
            repair_input["validation_error"] = str(first_error)
            repair_input["previous_response"] = raw_screenplay
            repair_input["instructions"] += (
                " Previous full-film screenplay FAILED strict validation. "
                "Generate a new, COMPLETE whole-film JSON from the original "
                "story. Fix the supplied validation_error while preserving all "
                "user-required events, ordering, character bindings and ending. "
                "Do not use partial JSON, scene deletions or ellipsis."
            )
            revised = self.rewrite("WHOLE_FILM_SCREENWRITER", repair_input)
            _atomic_text(root / "screenplay_9b_retry_raw.txt",
                         revised if isinstance(revised, str)
                         else json.dumps(revised, ensure_ascii=False))
            try:
                screenplay = validate_script(revised,
                                             picture_count=picture_count,
                                             max_seconds=max_seconds)
            except ProductionError as second_error:
                raise ProductionError(
                    f"9B first draft: {first_error}; one whole-film retry: "
                    f"{second_error}. Both raw responses saved; no H3 queued."
                ) from second_error
        # H3 accepts 24fps frame lengths on its native 5+17k grid.
        # Apply the timing conversion BEFORE camera design so no staged event
        # is truncated at render time. Film beats remain in the same order.
        requested_ms = sum(c["duration_ms"] for c in screenplay["clips"])
        original_durations = [c["duration_ms"] for c in screenplay["clips"]]
        frames = [5 + 17 * ((round(ms * 24 / 1000) - 5) // 17)
                  for ms in original_durations]
        if any(n < 124 for n in frames):
            raise ProductionError("Clip too short for the native H3 frame grid")
        # Spend the FULL movie's legal frame budget, not one truncated budget
        # per clip. 18x10s becomes about 179.42s, not 169.50s.
        budget = int(min(max_seconds * 24, requested_ms * 24 / 1000))
        while sum(frames) + 17 <= budget:
            candidates = [i for i, n in enumerate(frames) if (n + 17) / 24 <= 15]
            if not candidates:
                break
            best = max(candidates, key=lambda i: original_durations[i] * 24 / 1000 - frames[i])
            if original_durations[best] * 24 / 1000 <= frames[best]:
                break
            frames[best] += 17
        for clip, before, count in zip(screenplay["clips"], original_durations, frames):
            after = round(count * 1000 / 24)
            previous = -1
            for beat in clip["beats"]:
                beat["at_ms"] = round(beat["at_ms"] * after / before)
                if beat["at_ms"] <= previous or beat["at_ms"] >= after:
                    raise ProductionError("Native frame timing collapses authored beats")
                previous = beat["at_ms"]
            clip["duration_ms"] = after
            clip["render_frames"] = count
        camera_input = camera_task(screenplay)
        camera_raw = self.rewrite("WHOLE_FILM_CAMERA_ONLY", camera_input)
        _atomic_text(root / "camera_9b_raw.txt",
                     camera_raw if isinstance(camera_raw, str)
                     else json.dumps(camera_raw, ensure_ascii=False))
        camera, fallback = validate_cameras(camera_raw, screenplay)
        prompts = [compile_clip(screenplay, i, shots) for i, shots in enumerate(camera)]
        # No H3 work can begin until the entire plan and every prompt passes.
        serialized = [p.encode("utf-8") for p in prompts]
        script_json = json.dumps(screenplay, ensure_ascii=False, indent=2)
        camera_json = json.dumps(camera, ensure_ascii=False, indent=2)
        manifest = {
            "version": self.VERSION, "title": screenplay["title"],
            "duration_ms": sum(c["duration_ms"] for c in screenplay["clips"]),
            "requested_duration_ms": requested_ms,
            "screenplay_sha256": hashlib.sha256(script_json.encode("utf-8")).hexdigest(),
            "camera_sha256": hashlib.sha256(camera_json.encode("utf-8")).hexdigest(),
            "clip_count": len(prompts), "camera_fallback": fallback,
            "prompts": [{"index": i, "file": f"{i:02d}_prompt.txt",
                         "sha256": hashlib.sha256(data).hexdigest()}
                        for i, data in enumerate(serialized)],
            "render_status": "not_started",
        }
        root.mkdir(parents=True, exist_ok=True)
        _atomic_text(root / "screenplay.json", script_json)
        _atomic_text(root / "camera.json", camera_json)
        for index, prompt in enumerate(prompts):
            _atomic_text(root / f"{index:02d}_prompt.txt", prompt)
        _atomic_text(root / "ready.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        return manifest


def load_ready(project_dir):
    """Verify every sealed prompt before a separate renderer can consume it."""
    root = Path(project_dir)
    try:
        manifest = _json((root / "ready.json").read_text(encoding="utf-8"))
        for name, key in (("screenplay.json", "screenplay_sha256"),
                          ("camera.json", "camera_sha256")):
            content = (root / name).read_bytes()
            if hashlib.sha256(content).hexdigest() != manifest[key]:
                raise ProductionError("Sealed full-film planning data was altered")
        prompts = []
        for item in manifest["prompts"]:
            raw = (root / item["file"]).read_bytes()
            if hashlib.sha256(raw).hexdigest() != item["sha256"]:
                raise ProductionError("Sealed shooting prompt was altered")
            prompts.append(raw.decode("utf-8"))
        if len(prompts) != manifest["clip_count"]:
            raise ProductionError("Manifest clip count mismatch")
        return manifest, prompts
    except (FileNotFoundError, UnicodeDecodeError, KeyError, TypeError) as exc:
        raise ProductionError("Full film not ready for H3 rendering") from exc
