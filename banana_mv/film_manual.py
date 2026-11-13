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
from banana_mv.timed_slots import allocate_timed_chapters, parse_timed_source

CLIP = re.compile(
    r'(?im)^[ \t]*===\s*CLIP\s+([1-9]\d*)\s*'
    r'\(\s*(\d+(?:\.\d+)?)\s*s(?:ec(?:onds?)?)?\s*\)\s*===\s*$'
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
    # Adapt Film's SHOT syntax to MV's chapter allocator. Keep each shot intact.
    shots = list(re.finditer(
        r'(?im)^[ \t]*SHOT[ \t]+\d+[ \t]*[｜|:：][ \t]*(\d+(?:\.\d+)?)'
        r'\s*[-–—~～至]\s*(\d+(?:\.\d+)?)\s*s[^\n]*$', source))
    if shots:
        setup = source[:shots[0].start()]
        chapters = []
        for index, shot in enumerate(shots):
            stop = shots[index+1].start() if index+1 < len(shots) else len(source)
            chapters.append({'start':float(shot[1]), 'end':float(shot[2]),
                             'actions':[source[shot.end():stop].strip()], 'constraints':[]})
    else:
        timed = parse_timed_source(source)
        setup, chapters = timed if timed else ('', [])
    if chapters:
        if any(not 0 <= row['start'] < row['end'] <= total_seconds+1e-8 for row in chapters):
            raise ValueError('章節時間超出全片範圍。')
        fixed = '\n'.join(line for line in setup.splitlines()
            if re.match(r'^\s*(?:主角|角色|人物|固定場景|影片風格|影像風格|場景|主要道具|聲音設定|以.+(?:背景音樂|環境音效)|全片無對白|無旁白)', line)
            and not re.match(r'^\s*(?:故事|劇情|結局)', line))
        width = legal_frames(total_seconds/count, ceiling)/FPS
        windows = [{'start':i*width, 'seconds':width if i+1<count else max(width,total_seconds-i*width)}
                   for i in range(count)]

        def commission(chapter, phase, phases, previous):
            actions = chapter['actions']
            local = actions[phase*len(actions)//phases:(phase+1)*len(actions)//phases]
            context = 'ALREADY ESTABLISHED; continue without replay: '+previous if previous else ''
            return '\n'.join(filter(None, [context, *local])), previous

        prompts = allocate_timed_chapters(chapters, windows, commission, timeline='FILM')
        return [(width, '\n\n'.join(filter(None, [fixed, prompt]))) for prompt in prompts]
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
        if previous and req.get('python_manual_handoff') and 'PYTHON-OWNED SOURCE INTERVAL' not in event and 'USER-SPECIFIED FILM TIME' not in event:
            row['continuity_context'] = previous
        previous = next((line for line in reversed(event.splitlines())
                         if line.strip() and not re.match(r'^(?:鏡頭|攝影機|運鏡|配樂|音效|#)', line.strip())), previous)
        row.update(song_seconds=duration,segment_count=len(rows),fixed_reference_settings='')
    return {'title':title[:120],'duration':duration,'segments':rows,'shared_setup':''}
