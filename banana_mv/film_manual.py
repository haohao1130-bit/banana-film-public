"""Deterministic native H3 input, no LLM rewriting or screenplay invention.

Syntax:
=== CLIP 1 (12s) ===
subject_definitions: ...
summary: ...
retention_analysis: ...
detailed_description: ...
overall_soundscape: ...
non_diegetic_music: ...

Free-form text without CLIP markers uses one generation window.
"""
import math
import re

from banana_mv.core import FPS

CLIP = re.compile(
    r'(?im)^[ \t]*===\s*CLIP\s+([1-9]\d*)\s*'
    r'\(\s*(\d+(?:\.\d+)?)\s*s(?:ec(?:onds?)?)?\s*\)\s*===\s*$'
)
TIMED_HEADING = re.compile(
    r'(?m)^#{1,6}\s+[^\n]*?(\d{1,2}:\d{2}(?:\.\d+)?)\s*[-–—~～至]\s*'
    r'(\d{1,2}:\d{2}(?:\.\d+)?)[^\n]*$'
)
CLIP_LIKE = re.compile(r'(?im)^[ \t]*===\s*CLIP\b')


def split_native_h3(story, single_seconds):
    """Return authored (seconds, prompt text) pairs.

    Broken CLIP boundaries must error, never be silently sent to the 9B writer.
    """
    source = story.strip()
    fence = re.fullmatch(r'```(?:text|h3|plaintext)?[ \t]*\n([\s\S]*?)\n```[ \t]*', source, re.I)
    if fence:
        source = fence[1].strip()
    matches = list(CLIP.finditer(source))
    if not matches:
        if CLIP_LIKE.search(source):
            raise ValueError('CLIP 標記需為 === CLIP 1 (12s) ===，每段從 1 連號。')
        return [(float(single_seconds), source)]
    if source[:matches[0].start()].strip():
        raise ValueError('第一個 CLIP 標記前不能有未分段的提示詞。')
    if len(matches) > 34:
        raise ValueError('手動全咒最多 34 段。')
    result = []
    for i, match in enumerate(matches):
        if int(match[1]) != i + 1:
            raise ValueError('CLIP 必須從 1 開始依序連號。')
        text = source[match.end():matches[i+1].start() if i+1 < len(matches) else len(source)].strip()
        if CLIP_LIKE.search(text):
            raise ValueError(f'第 {i+1} 段含錯誤 CLIP 標記。')
        result.append((float(match[2]), text))
    return result


def distribute_manual_prompt(clips, total_seconds, ceiling):
    """Split an unmarked long prompt at its existing paragraph or sentence boundaries."""
    if len(clips) != 1 or total_seconds <= ceiling:
        return clips
    _, source = clips[0]
    largest = max(range(124, math.floor(ceiling * FPS) + 1, 17)) / FPS
    count = math.ceil(total_seconds / largest)
    headings = list(TIMED_HEADING.finditer(source))
    if headings:
        def seconds(clock):
            minutes, rest = clock.split(':')
            return int(minutes) * 60 + float(rest)

        width = total_seconds / count
        assigned = [[] for _ in range(count)]
        for i, heading in enumerate(headings):
            begin, end = map(seconds, heading.groups())
            stop = headings[i + 1].start() if i + 1 < len(headings) else len(source)
            if not 0 <= begin < end <= total_seconds + 1e-8:
                raise ValueError('章節時間超出全片範圍。')
            actions = source[heading.end():stop].strip().splitlines()
            actions = [action for action in actions if action.strip()]
            slots = [slot for slot in range(count)
                     if min(end, (slot + 1) * width) > max(begin, slot * width)]
            for phase, slot in enumerate(slots):
                first = phase * len(actions) // len(slots)
                last = (phase + 1) * len(actions) // len(slots)
                assigned[slot].extend(actions[first:last])
        setup = source[:headings[0].start()].strip()
        return [(width, '\n'.join(filter(None, [setup, *actions])) or
                 'Continue the established scene and ongoing action.')
                for actions in assigned]
    units = [part.strip() for part in re.split(r'\n+|(?<=[。！？!?；;])\s*|(?<=\.)[ \t]+', source)
             if part.strip()]
    if len(units) < count:
        raise ValueError(f'全片 {total_seconds:g} 秒需分成 {count} 段。請用換行分開各段事件，或標出 CLIP 邊界。')
    cuts = [round(i * len(units) / count) for i in range(count + 1)]
    return [(total_seconds / count, '\n'.join(units[cuts[i]:cuts[i+1]]))
            for i in range(count)]


def legal_frames(seconds, ceiling):
    if not isinstance(seconds, (int,float)) or isinstance(seconds,bool) or not math.isfinite(seconds):
        raise ValueError('手動分段秒數必須是正確的有限數字。')
    if not 124/FPS <= seconds <= ceiling + 1e-8:
        raise ValueError(f'手動段落需介於 {124/FPS:.3f}–{ceiling:g} 秒；超長全咒須明確拆成 CLIP。')
    # The valid native AV counts are 5+17*k; choose the closest legal count
    # rather than the legacy floor so a 35-second commissioned film can align.
    candidates=range(124,math.floor(ceiling*FPS)+1,17)
    try:
        return min(candidates,key=lambda frames:(abs(frames/FPS-seconds),frames))
    except ValueError as e:
        raise ValueError('這個片段上限沒有 H3 合法影格數。') from e


def make_manual_plan(clips, req, normalize, map_mentions, image_count, validator,
                     title='手動 H3 原生攝影'):
    """Validate authored material, preserve *every* original shot and six fields."""
    if not 1 <= len(clips) <= 34:
        raise ValueError('手動 H3 需提供 1–34 段。')
    rows=[]
    frame_start=0
    total_authored=sum(seconds for seconds,_ in clips)
    if not math.isfinite(total_authored):
        raise ValueError('總時長無效。')
    cap = float(req['max_seconds'])
    target = float(req.get('target_seconds',cap))
    tolerance=float(req.get('timeline_tolerance',0))
    if total_authored > target + tolerance + 1e-8:
        raise ValueError(f'手動全咒總時長 {total_authored:.2f} 秒超過本次設定 {target:g} 秒。')
    if req.get('target_is_exact') and abs(total_authored-target)>tolerance + 1e-8:
        raise ValueError(f'手動全咒 {total_authored:.2f} 秒與指定總長 {target:g} 秒不一致。')
    for i,(seconds,text) in enumerate(clips):
        if not isinstance(text,str) or not text.strip():
            raise ValueError(f'第 {i+1} 段是空的。')
        mapped=normalize(map_mentions(req,text,image_count),image_count)
        frames=legal_frames(seconds,float(req['segment_seconds']))
        actual=frames/FPS
        validator(mapped,actual,req['sound_mode'])
        row={'index':i,'start_frame':frame_start,'frames':frames,
             'start':frame_start/FPS,'seconds':actual,'model_frames':frames,
             'status':'waiting','director_mode':'story',
             'director_plan':{'index':i,'mode':'story','event':mapped},
             'manual_h3_prompt':mapped}
        rows.append(row)
        frame_start+=frames
    duration=frame_start/FPS
    if duration>min(300.0,cap)+1e-8:
        raise ValueError(f'對齊合法 H3 幀數後是 {duration:.2f} 秒，超出本次上限。請微調各段秒數。')
    if req.get('target_is_exact') and abs(duration-target)>tolerance + 1e-8:
        raise ValueError(f'合法影格對齊後為 {duration:.2f} 秒，超出指定 {target:g}±{tolerance:g} 秒；請調整 CLIP 長度。')
    previous = ''
    for row in rows:
        event = row['director_plan']['event']
        if previous and req.get('python_manual_handoff'):
            row['continuity_context'] = previous
        previous = next((line for line in reversed(event.splitlines())
                         if line.strip() and not re.match(r'^(?:鏡頭|攝影機|運鏡|配樂|音效|#)', line.strip())), previous)
        row.update(song_seconds=duration,segment_count=len(rows),fixed_reference_settings='')
    return {'title':title[:120],'duration':duration,'segments':rows,'shared_setup':''}
