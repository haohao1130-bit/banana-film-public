"""Pure deterministic short-film production planner.

The whole-story 9B writer supplies ordered atomic story beats, not clip slots.
Python assigns legal H3 slots, carries EXPLICIT state changes and gives the
camera 9B only the current slot. No old banana_mv film code is imported.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import math

FPS = 24
GRID = 17
BASE = 5
MIN_FRAMES = 124
CHARACTER_FIELDS = frozenset(("location", "position", "facing", "held_props", "appearance", "emotion"))
PROP_FIELDS = frozenset(("holder", "location", "status"))


class FilmPlanError(ValueError):
    """Invalid screenplay or impossible deterministic slot assignment."""


def _digest(value):
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def _seconds(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise FilmPlanError(field + " 必須為正的有限秒數。")
    return float(value)


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise FilmPlanError(field + " 必須有內容。")
    return value.strip()


def _state(raw):
    if not isinstance(raw, dict) or set(raw) != {"characters", "props"}:
        raise FilmPlanError("initial_state 必須包含 characters 與 props。")
    for category, allowed in (("characters", CHARACTER_FIELDS), ("props", PROP_FIELDS)):
        entries = raw[category]
        if not isinstance(entries, dict):
            raise FilmPlanError(category + " 必須是角色或道具物件。")
        for key, values in entries.items():
            _text(key, category + " id")
            if not isinstance(values, dict) or set(values) - allowed:
                raise FilmPlanError(category + "/" + key + " 包含不支援的狀態欄位。")
    return deepcopy(raw)


def _changes(raw, state, beat_id):
    if raw is None:
        return {"characters": {}, "props": {}}
    if not isinstance(raw, dict) or set(raw) - {"characters", "props"}:
        raise FilmPlanError(beat_id + " 的 changes 格式不正確。")
    result = {}
    for category, allowed in (("characters", CHARACTER_FIELDS), ("props", PROP_FIELDS)):
        updates = raw.get(category, {})
        if not isinstance(updates, dict):
            raise FilmPlanError(beat_id + " 的 " + category + " changes 必須是物件。")
        result[category] = {}
        for key, attributes in updates.items():
            if key not in state[category] or not isinstance(attributes, dict) or set(attributes) - allowed:
                raise FilmPlanError(beat_id + " 修改未知角色、道具或保留欄位：" + str(key))
            result[category][key] = deepcopy(attributes)
    return result


def _beats(raw, initial):
    if not isinstance(raw, list) or not 1 <= len(raw) <= 160:
        raise FilmPlanError("beats 必須有 1–160 個原子事件。")
    seen = set()
    result = []
    for i, beat in enumerate(raw):
        if not isinstance(beat, dict):
            raise FilmPlanError("事件必須是物件。")
        identifier = _text(beat.get("id"), "beat.id")
        if identifier in seen:
            raise FilmPlanError("重複事件 ID：" + identifier)
        seen.add(identifier)
        actors = beat.get("actors", [])
        if not isinstance(actors, list) or len(actors) != len(set(map(str, actors))):
            raise FilmPlanError(identifier + " 的 actors 必須是無重複清單。")
        if any(not isinstance(actor, str) or actor not in initial["characters"] for actor in actors):
            raise FilmPlanError(identifier + " 引用了未登記角色。")
        dialogue = beat.get("dialogue", [])
        if not isinstance(dialogue, list):
            raise FilmPlanError(identifier + " 的 dialogue 必須是清單。")
        spoken = []
        for line in dialogue:
            if not isinstance(line, dict) or line.get("speaker") not in initial["characters"]:
                raise FilmPlanError(identifier + " 的台詞沒有有效說話者。")
            spoken.append({"speaker": line["speaker"], "text": _text(line.get("text"), "dialogue.text"),
                           "language": str(line.get("language", ""))})
        if "cut_after" in beat and not isinstance(beat["cut_after"], bool):
            raise FilmPlanError(identifier + " 的 cut_after 必須是布林值。")
        result.append({"id": identifier, "action": _text(beat.get("action"), identifier + ".action"),
                       "actors": actors, "seconds_hint": _seconds(beat.get("seconds_hint"), identifier + ".seconds_hint"),
                       "dialogue": spoken, "changes": _changes(beat.get("changes"), initial, identifier),
                       "cut_after": beat.get("cut_after", False)})
    return result


def _frames(hint, maximum):
    """Choose closest legal native 5+17*k video frames without exceeding max."""
    cap = int(math.floor(maximum * FPS + 1e-9))
    upper = (cap - BASE) // GRID
    lower = (MIN_FRAMES - BASE) // GRID
    if upper < lower:
        raise FilmPlanError("每段上限不足以容納 H3 最短合法片段。")
    k = round((hint * FPS - BASE) / GRID)
    return BASE + GRID * max(lower, min(upper, k))


def _partition(beats, max_clip_seconds, target_min_seconds):
    """Order-preserving DP; no beat is repeated or divided, and hard cuts stay hard."""
    n = len(beats)
    best = [None] * (n + 1)
    best[n] = (0.0, [])
    for i in range(n - 1, -1, -1):
        duration = 0.0
        for j in range(i, n):
            duration += beats[j]["seconds_hint"]
            if duration > max_clip_seconds + 1e-9:
                break
            if duration >= MIN_FRAMES / FPS - 1e-9 and best[j + 1] is not None:
                frames = _frames(duration, max_clip_seconds)
                actual = frames / FPS
                shortfall = max(0.0, min(target_min_seconds, max_clip_seconds) - duration)
                penalty = shortfall ** 2 + abs(actual - duration) / 8 + 0.15
                candidate = (penalty + best[j + 1][0], [(i, j + 1, frames)] + best[j + 1][1])
                if best[i] is None or candidate[0] < best[i][0] - 1e-9:
                    best[i] = candidate
            if beats[j]["cut_after"]:
                break
    if best[0] is None:
        raise FilmPlanError("事件無法組成合法 H3 片段；請讓編劇細分過長事件，或合併過短事件，不能剪斷台詞。")
    return best[0][1]


def _apply(state, changes):
    for category in ("characters", "props"):
        for key, values in changes[category].items():
            state[category][key].update(deepcopy(values))


def compile_film(screenplay, *, max_seconds=180, max_clip_seconds=15,
                 target_min_seconds=10):
    """Compile an approved atomic-beat screenplay into Python-owned H3 slots.

    No rewriting, model calls, narration inference, FFmpeg or background actions.
    Changes only express outcomes explicitly authorized by the approved script.
    """
    if not isinstance(screenplay, dict):
        raise FilmPlanError("screenplay 必須是物件。")
    ceiling = _seconds(max_seconds, "max_seconds")
    clip_ceiling = _seconds(max_clip_seconds, "max_clip_seconds")
    if ceiling > 180 or clip_ceiling > 15 or clip_ceiling > ceiling:
        raise FilmPlanError("短片上限最多 180 秒，單段最多 15 秒。")
    target_min = _seconds(target_min_seconds, "target_min_seconds")
    title = _text(screenplay.get("title"), "title")
    shared = screenplay.get("shared_setup", "")
    if not isinstance(shared, str):
        raise FilmPlanError("shared_setup 只能放固定身份、場景設定文字。")
    initial = _state(screenplay.get("initial_state"))
    beats = _beats(screenplay.get("beats"), initial)
    if sum(b["seconds_hint"] for b in beats) > ceiling + 1e-9:
        raise FilmPlanError("事件估計總長超過短片硬上限，不能無聲壓縮事件或台詞。")
    groups = _partition(beats, clip_ceiling, target_min)
    current = deepcopy(initial)
    start = 0
    clips = []
    completed = []
    for index, (a, b, frames) in enumerate(groups):
        opening = deepcopy(current)
        events = []
        for beat in beats[a:b]:
            events.append({k: deepcopy(beat[k]) for k in ("id", "action", "actors", "dialogue")})
            _apply(current, beat["changes"])
        clips.append({"index": index, "start_frame": start, "frames": frames,
                      "start_seconds": start / FPS, "seconds": frames / FPS,
                      "event_ids": [e["id"] for e in events],
                      "events": events, "state_at_open": opening,
                      "state_at_close": deepcopy(current),
                      "previous_event_id": completed[-1] if completed else None,
                      "boundary": "final" if b == len(beats) else "intermediate"})
        completed.extend(e["id"] for e in events)
        start += frames
    if start > math.floor(ceiling * FPS + 1e-9):
        raise FilmPlanError("合法影格加總超過短片上限；請調整事件時間提示。")
    result = {"engine": "python_owned_film_v2", "version": 1,
              "title": title, "shared_setup": shared,
              "source_sha256": _digest(screenplay),
              "duration_frames": start, "duration_seconds": start / FPS,
              "clips": clips, "visual_verified": False}
    result["plan_sha256"] = _digest(result)
    return result


def shot_commission(plan, clip_index):
    """Only the currently assigned local clip, never full future beats."""
    if not isinstance(clip_index, int) or isinstance(clip_index, bool):
        raise FilmPlanError("clip_index 必須為整數。")
    clips = plan["clips"]
    if not 0 <= clip_index < len(clips):
        raise FilmPlanError("不存在指定的片段。")
    clip = clips[clip_index]
    return {"contract": "film_v2_local_camera_only", "shared_setup": plan["shared_setup"],
            "index": clip_index, "seconds": clip["seconds"],
            "events": deepcopy(clip["events"]),
            "known_opening_state": deepcopy(clip["state_at_open"]),
            "expected_local_result": deepcopy(clip["state_at_close"]),
            "already_completed_event_id": clip["previous_event_id"],
            "boundary": clip["boundary"],
            "instruction": ("Film ONLY the commissioned actions in order. Preserve named speakers, "
                            "props, identities and incoming physical state. Camera freedom is allowed; "
                            "no future actions, invented plot, restaging or automatic intermediate ending.")}
