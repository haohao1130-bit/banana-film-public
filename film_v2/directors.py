"""9B stages for FILM V2. Creativity in screenplay; camera never sees future beats."""
from __future__ import annotations
import json
from pathlib import Path
import re
import uuid

from PIL import Image, ImageOps
from banana_mv import services as backend
from banana_mv.direction_contract import validate_h3_sections
from banana_mv.scene_state import parse_object
from .production import compile_film, shot_commission, FilmPlanError

WRITER_SYSTEM = """You are the screenwriter of a self-contained SHORT FILM, not a music video.
Create a complete causally ordered screenplay from the user's premise. Preserve named
people, picture bindings, relationships, key dialogue, specified actions and ending.
FAITHFUL means no invented plot, AUTO may develop within the user's premise.
No compulsory combat, twists, musical score, repeated beats, filler or slow-motion.
You are NOT designing camera shots. Python will independently allocate H3 clips.

Return one valid JSON object only, with:
{"title":"...","shared_setup":"fixed identities, <Picture N> actor bindings and geography ONLY",
"initial_state":{"characters":{"A":{"location":"...","position":"...","appearance":"..."}},
"props":{"P":{"holder":"...","status":"..."}}},
"beats":[{"id":"b1","action":"concrete visible event with explicitly named actors",
"actors":["A"],"seconds_hint":6,"dialogue":[{"speaker":"A","text":"...","language":"zh-TW"}],
"changes":{"characters":{"A":{"location":"..."}},"props":{}},"cut_after":false}]}

REQUIRED:
- Give every visible or speaking person a stable distinct character ID and initial_state.
- Every actor in actors and every dialogue speaker exists in initial_state.characters.
- initial_state is the exact factual scene OPENING, not final state.
- Explicitly declare event consequences in changes using only these character properties:
  location, position, facing, held_props, appearance, emotion.
  Props may change holder, location, status.
- Named cast and picture references are stable; references are identities, not pose commands.
- Each beat is atomic with a realistic positive seconds_hint. A spoken line must remain in
  one beat and its time estimate must include spoken delivery and listener response.
- Each beat occurs once. Do not encode future story in shared_setup or the opening state.
- Only use cut_after=true for a mandatory scene/time boundary.
- Make beats small enough for the single H3 clip cap; Python may group adjacent beats.
- No extra keys required. Keep JSON compact enough for 8192 output tokens.
- sound_mode=ambient: dialogue must be [] for ALL beats and no singing or voices.
- sound_mode=dialogue: use dialogue only when the story calls for speech.
- Produce a natural arc, actual causal consequences and an ending within max_seconds.
- Target duration is a CEILING, not a mandate to pad or repeat the ending.
All narration and actions must be attributable to the correct named character.
"""

CAMERA_SYSTEM = """You are the cinematographer for EXACTLY ONE already approved short-film clip.
You are not a screenwriter or editor of story events.
Only camera staging, composition, lens, motivated cuts, light, actor performance timing
and sonic staging may be authored. Preserve every local action, speaker, line, prop
ownership, physical position, entrance, exit and required result.
The given local commission contains everything you may know; do not infer missing
earlier events or future ending. Never repeat the previous completed event.
The shared_setup contains fixed identities and world, not mandatory cast attendance.
A cut changes CAMERA viewpoint, not character actions or elapsed time. Actor movement
is motivated by current events. No mandatory cut count, heroic pose or extra climax.
Use stable <Subject N> and <Picture N> where relevant; do not invent image references.
First segment establishes scene; following segments begin in their provided physical
state. Intermediate segments never self-conclude unless this clip requests resolution.
Each [Shot N] is in playback order. [Shot 1] begins immediately, later shots each
use 'At MM:SS.mmm' timestamps strictly increasing and inside the delivered duration.
For actual dialogue use stable (S1), (S2) voice IDs tied to characters throughout;
only a speaking character gets a voice ID. Use <d>[Language] spoken text</d>.
Do not insert <Audio N>, fully_copy, lock_source, source lyrics or music video rules.
Film native H3 generates both picture and sound. No soundtrack unless requested.
Ambient mode: no spoken voices, dialogue, chanting, singing or speaker tags.
No captions, subtitles or text overlays unless explicitly commissioned.
Return the FULL original MiniMax H3 six-section prompt, no JSON:
subject_definitions:
summary:
retention_analysis:
detailed_description:
overall_soundscape:
non_diegetic_music:
"""

def pictures(paths):
    payload = []
    for index, path in enumerate(paths, 1):
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((768, 768))
            payload.extend([("text", f"<Picture {index}>:"), ("image", image.copy())])
    return payload


def source_to_picture(text, image_slots):
    """User-visible 1-9 slots never shift if the user leaves a gap."""
    mapping = {}
    logical = 0
    for slot, asset in enumerate(image_slots, 1):
        if asset is not None:
            logical += 1
            mapping[slot] = logical
    def replace(m):
        idx = int(m.group(1))
        if idx not in mapping:
            raise FilmPlanError(f"@圖片{idx} 尚未選擇參考圖。")
        return f"<Picture {mapping[idx]}>"
    return re.sub(r"@(?:圖片|图片|image)\s*(\d+)", replace, text, flags=re.I)


def screenplay(cfg, req, originals, work, *, instruction=None, current=None):
    source = {"story": source_to_picture(req["prompt"], req["image_slots"]),
              "image_bindings": {str(i + 1): name for i, name in enumerate(req["image_slots"]) if name},
              "max_seconds": req["max_seconds"], "max_clip_seconds": req["segment_seconds"],
              "sound_mode": req["sound_mode"], "style": req["visual_style"],
              "adaptation": "AUTO" if req["auto_director"] else "FAITHFUL"}
    if instruction:
        source["revision_instruction"] = instruction
        source["current_approved_draft"] = current
    system = WRITER_SYSTEM
    if instruction:
        system += ("\nREVISION: Update only requested story details while preserving all unaffected "
                   "beats, identities, dialogue and causal links. Return the complete JSON.")
    parts = [("text", json.dumps(source, ensure_ascii=False))] + pictures(originals)
    repair = ""
    errors = []
    for attempt in range(req["rewrite_retries"] + 1):
        call = parts + ([("text", repair)] if repair else [])
        raw = backend.rewrite_local(cfg, system, call, uuid.uuid4().hex[:8])
        (Path(work) / f"v2_story_raw_{attempt:02d}.txt").write_text(raw, encoding="utf-8")
        try:
            doc = parse_object(raw)
            if not isinstance(doc, dict):
                raise FilmPlanError("編劇交付不是 JSON 物件。")
            if req["sound_mode"] == "ambient" and any(b.get("dialogue") for b in doc.get("beats", [])):
                raise FilmPlanError("環境音模式不得產生對白。")
            plan = compile_film(doc, max_seconds=req["max_seconds"],
                                max_clip_seconds=req["segment_seconds"],
                                target_min_seconds=req["target_min_seconds"])
            return doc, plan
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            errors.append(str(exc))
            repair = ("The previous screenplay was invalid. Repair the JSON; preserve story "
                      "requirements, all character identities and causal outcomes. Do not shorten "
                      "or invent dialogue to bypass timing. Error: " + str(exc))
    raise FilmPlanError("9B 劇本未通過 Python 規劃：" + " | ".join(errors[-2:]))


def _normalize_camera(raw, picture_count, seconds, sound_mode):
    text = raw.strip()
    validate_h3_sections(text)
    if re.search(r"<\s*(?:Audio|Video)\s*\d+\s*>|\bfully_copy\b|\block_source\b", text, re.I):
        raise FilmPlanError("原生影音短片不可引用外部音源、來源影片或 MV 鎖音規則。")
    def picture(m):
        number = int(m.group(1))
        if not 1 <= number <= picture_count:
            raise FilmPlanError(f"攝影稿引用不存在的 <Picture {number}>。")
        return f"<Picture {number}>"
    text = re.sub(r"<\s*(?:Picture|Image)\s*(\d+)\s*>", picture, text, flags=re.I)
    detail = text.split("detailed_description:", 1)[1].split("overall_soundscape:", 1)[0]
    shots = list(re.finditer(r"\[Shot\s+(\d+)\]", detail))
    if not shots:
        raise FilmPlanError("攝影稿缺少 [Shot 1]。")
    if len(shots) != len(re.findall(r"\[Shot\b", detail)):
        raise FilmPlanError("攝影稿 Shot 標記不完整。")
    prior = 0.
    for index, item in enumerate(shots):
        if int(item.group(1)) != index + 1:
            raise FilmPlanError("Shot 編號不連續。")
        body = detail[item.end():shots[index + 1].start() if index + 1 < len(shots) else len(detail)]
        at = re.match(r"\s*At\s+(\d{2}):(\d{2})\.(\d{3})\b", body)
        if index == 0 and at:
            raise FilmPlanError("第一鏡不能加切鏡時間碼。")
        if index > 0:
            if at is None:
                raise FilmPlanError("後續鏡頭必須有 At MM:SS.mmm 時間碼。")
            minute, sec, milli = map(int, at.groups())
            value = minute * 60 + sec + milli / 1000
            if sec >= 60 or not prior < value < seconds:
                raise FilmPlanError("切鏡時間超出當段或不遞增。")
            prior = value
        if not body.strip():
            raise FilmPlanError("鏡頭沒有拍攝內容。")
    if sound_mode == "ambient" and (re.search(r"\(S\d+\)", text) or "<d>" in text):
        raise FilmPlanError("環境音模式不能出現人聲與台詞標記。")
    return text


def camera(cfg, req, plan, index, originals, work, *, tail=None,
           correction=None, base=None, version=1):
    commission = shot_commission(plan, index)
    images = ([tail] if tail else []) + list(originals)
    offset = int(bool(tail))
    # In one-frame mode the preceding tail consumes Picture 1; original refs shift.
    def adjust(value):
        if isinstance(value, str):
            return re.sub(r"<Picture\s+(\d+)>",
                          lambda m: f"<Picture {int(m.group(1)) + offset}>", value)
        if isinstance(value, list):
            return [adjust(x) for x in value]
        if isinstance(value, dict):
            return {k: adjust(v) for k, v in value.items()}
        return value
    task = adjust(commission)
    task.update({"sound_mode": req["sound_mode"], "visual_style": req["visual_style"],
                 "picture_count": len(images), "dialogue_rule": "exact speaker and words",
                 "continuous_visual_reference": "<Picture 1> is previous frame only" if tail else None})
    if correction:
        task["local_camera_correction"] = correction
        task["previous_camera_prompt"] = base
    if req["mode"] == "chain5" and index > 0:
        task["chain5"] = ("Five preceding frames are provided directly as motion guide, "
                          "not as actors or reference picture IDs. Do not replay the five frames.")
    system = Path(cfg["guides"]["ref"]).read_text(encoding="utf-8") + "\n" + CAMERA_SYSTEM
    prompt = [("text", json.dumps(task, ensure_ascii=False))] + pictures(images)
    errors = []
    for attempt in range(req["rewrite_retries"] + 1):
        user_parts = prompt if not errors else prompt + [("text", "Correct the complete six-section prompt. Error: " + errors[-1])]
        raw = backend.rewrite_local(cfg, system, user_parts, uuid.uuid4().hex[:8])
        (Path(work) / f"{index:02d}_camera_v{version}_raw_{attempt:02d}.txt").write_text(raw, encoding="utf-8")
        try:
            return _normalize_camera(raw, len(images), commission["seconds"], req["sound_mode"])
        except (FilmPlanError, ValueError) as exc:
            errors.append(str(exc))
    raise FilmPlanError("9B 攝影稿驗證失敗：" + errors[-1])
