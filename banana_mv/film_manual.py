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
from banana_mv.film_actor_state import _opening_actor_state, _advance_actor_state, _actor_state_lines
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


def _shot_action_units(body):
    """Partition only authored performance; preserve speaking cue + its line."""
    units=[]
    for raw in body.splitlines():
        line=raw.strip()
        if not line:
            continue
        if units and units[-1].endswith(('：', ':')) and re.match(r'^\(S\d+\)\s*[「『<]', line):
            units[-1]+='\n'+line
        else:
            units.append(line)
    return units


def distribute_manual_prompt(clips, total_seconds, ceiling):
    """Split an unmarked long prompt at its existing paragraph or sentence boundaries."""
    if len(clips) != 1:
        return clips
    _, source = clips[0]
    largest = max(range(124, math.floor(ceiling * FPS) + 1, 17)) / FPS
    count = math.ceil(total_seconds / largest)
    shots = list(re.finditer(
        r'(?im)^[ \t]*(?:#{1,6}[ \t]+)?SHOT[ \t]+(\d+)[ \t]*[｜|:：][ \t]*(\d+(?:\.\d+)?)'
        r'\s*[-–—~～至]\s*(\d+(?:\.\d+)?)\s*(?:秒(?:鐘)?|s(?:ec)?\b)[^\n]*$', source))
    if shots:
        setup = source[:shots[0].start()]
        end = re.search(r'(?m)^\s*(?:聲音與表演控制|電影攝影控制|核心敘事)[ \t]*[:：]?[ \t]*$', source[shots[-1].end():])
        body_end = shots[-1].end() + end.start() if end else len(source)
        appendix = source[body_end:]
        chapters = []
        for index, shot in enumerate(shots):
            stop = shots[index+1].start() if index+1 < len(shots) else body_end
            body = source[shot.end():stop].strip()
            notes = re.findall(rf'(?im)^[ \t]*SHOT[ \t]+0*{int(shot[1])}[：:]([^\n]+)$', appendix)
            for line in appendix.splitlines():
                if re.match(r'^\s*配樂', line):
                    notes.extend(clause for clause in re.split(r'[，。；]', line)
                                 if re.search(rf'\bSHOT\s+0*{int(shot[1])}(?!\d)', clause, re.I))
            actions=_shot_action_units(body)
            if not actions:
                raise ValueError(f'SHOT {int(shot[1]):02d} 沒有可拍攝的演出內容。')
            chapters.append({'start':float(shot[2]), 'end':float(shot[3]),
                             'actions':actions, 'constraints':notes})
        global_audio = re.split(r'(?m)^[ \t]*(?:電影攝影控制|核心敘事)[ \t]*[:：]?[ \t]*$', appendix, maxsplit=1)[0]
        setup += '\n' + '\n'.join(
            line for line in global_audio.splitlines()
            if re.match(r'^\s*(?:全片使用|[(]S[12][)]|對白必須|允許自然|背景使用|不加入|不擅自)', line)
            and not re.search(r'\bSHOT\s+\d+', line, re.I))
    else:
        timed = parse_timed_source(source)
        setup, chapters = timed if timed else ('', [])
    if chapters:
        if any(not 0 <= row['start'] < row['end'] <= total_seconds+1e-8 for row in chapters):
            raise ValueError('章節時間超出全片範圍。')
        fixed = '\n'.join(line for line in setup.splitlines()
            if re.match(r'^\s*(?:主角|角色|人物外貌|固定場景|影片風格|影像風格|場景|主要道具|聲音設定|以.+(?:背景音樂|環境音效)|全片無對白|無旁白|\\?<Picture\s+\d+>|[(]S[12][)]|16:9|冷調|遵守180|全片使用|對白必須|允許自然|背景使用|不加入|不擅自)', line)
            and not re.search(r'最後才|結局|修復AI|修電腦', line))
        # Quantize the full timeline once, then distribute legal frame counts.
        minimum = 124
        maximum = math.floor(ceiling * FPS)
        steps = round((total_seconds * FPS - count * minimum) / 17)
        steps = max(0, min(steps, count * ((maximum - minimum) // 17)))
        base, extra = divmod(steps, count)
        lengths = [(minimum + 17 * (base + (i < extra))) / FPS for i in range(count)]
        scale = total_seconds / sum(lengths)
        windows = []
        cursor = 0.0
        for length in lengths:
            windows.append({'start':cursor, 'seconds':length * scale})
            cursor += length * scale

        def commission(chapter, phase, phases, previous):
            actions = chapter['actions']
            # First assign the earlier authored beats, rather than allocating
            # only an empty camera instruction in the preceding clip.
            first = math.ceil(phase*len(actions)/phases)
            last = math.ceil((phase+1)*len(actions)/phases)
            local = actions[first:last]
            # Historical Chinese prose in [Shot] may be spoken aloud by H3.
            # Existing actions/wardrobe are represented by visual references and
            # structured actor state; never inject ALREADY ESTABLISHED dialogue.
            return '\n'.join(local), local[-1] if local else previous

        prompts = allocate_timed_chapters(
            chapters, windows, commission, timeline='FILM',
            skip_empty_commissions=True)
        if shots:
            state = _opening_actor_state(setup, chapters)
            return [(length, compile_storyboard_slot(fixed, prompt, length, window['seconds'], state))
                    for length, prompt, window in zip(lengths, prompts, windows)]
        return [(length, '\n\n'.join(filter(None, [fixed, prompt])))
                for length, prompt in zip(lengths, prompts)]
    if total_seconds <= ceiling:
        return clips
    units = [part.strip() for part in re.split(r'\n+|(?<=[。！？!?；;])\s*|(?<=\.)[ \t]+', source)
             if part.strip()]
    grouped = []
    for unit in units:
        if grouped and grouped[-1].endswith(('：', ':')) and re.match(r'^\(S\d+\)', unit):
            grouped[-1] += '\n' + unit
        else:
            grouped.append(unit)
    units = grouped
    if len(units) < count:
        raise ValueError(f'全片 {total_seconds:g} 秒需分成 {count} 段。請用換行分開各段事件，或標出 CLIP 邊界。')
    cuts = [round(i * len(units) / count) for i in range(count + 1)]
    return [(total_seconds / count, '\n'.join(units[cuts[i]:cuts[i+1]]))
            for i in range(count)]


def compile_storyboard_slot(fixed, prompt, length, source_length, state=None):
    """Turn the MV allocator's local assignments into native Ref2VA fields."""
    assigned = re.compile(r'(?m)^USER-SPECIFIED FILM TIME [^\n]*?'
                          r'inside THIS clip is ([\d.]+)–[\d.]+s\.[^\n]*\n')
    matches = list(assigned.finditer(prompt))
    opening = _actor_state_lines({kind: item for kind, item in (state or {}).items()
                                  if item.get('changed')})
    shots = []
    previous_ms = 0
    for i, match in enumerate(matches):
        stop = matches[i+1].start() if i+1 < len(matches) else len(prompt)
        body = prompt[match.end():stop].strip()
        parts=body.split('Constraints for THIS chapter only',1)
        # Only current-clip performed action may enter H3's [Shot] body.
        # This also sanitizes previously stored allocator text when regenerated.
        performance='\n'.join(line for line in parts[0].splitlines()
            if line.strip() and not line.lstrip().startswith(
                ('ALREADY ESTABLISHED;', 'ALREADY ESTABLISHED:',
                 'PYTHON-OWNED SOURCE INTERVAL')))
        if not performance.strip():
            continue
        if state:
            for line in performance.splitlines():
                if not re.search(r'^\s*ALREADY ESTABLISHED|\(S\d+\)|[「」『』]', line):
                    before={kind:item['status'] for kind,item in state.items()}
                    _advance_actor_state(state,line)
                    for kind,item in state.items():
                        if item['status']!=before[kind]:
                            item['changed']=True
        body=performance + ('\nConstraints for THIS chapter only'+parts[1] if len(parts)>1 else '')
        body=re.sub(r'(\(S\d+\))[ \t]*「([^」]+)」',
                    r'\1 <d>[Chinese] \2</d>',body)
        prefix = f'[Shot {len(shots)+1}]'
        if shots:
            ms = max(previous_ms+1, round(float(match[1]) * length/source_length * 1000))
            minutes, remaining = divmod(ms, 60000)
            seconds, millis = divmod(remaining, 1000)
            prefix += f' At {minutes:02d}:{seconds:02d}.{millis:03d},'
            previous_ms = ms
        shots.append(prefix + ' ' + body)
    details = '\n\n'.join(shots) if shots else '[Shot 1] Continue the established scene.'
    if opening:
        details = details.replace('[Shot 1] ', '[Shot 1] Starting wardrobe state: '
                                  + opening + '\nContinue this state. Perform only the current shot actions.\n', 1)
    refs = sorted(set(re.findall(r'<Picture (\d+)>', fixed + '\n' + details)), key=int)
    retention = '\n'.join(f'<Picture {ref}>: preserve referenced identity and appearance.' for ref in refs)
    return ('subject_definitions:\n' + (fixed or 'Use the actors and scene specified in the shots.')
            + '\n\nsummary:\nFilm the assigned shots in order within '
            + f'{length:.3f} seconds. Preserve the written lines and speaker IDs.'
            + '\n\nretention_analysis:\n' + (retention or 'Preserve established appearance and continuity.')
            + '\n\ndetailed_description:\n' + details
            + '\n\noverall_soundscape:\nFollow the specified voices, dialogue, and scene sounds.'
            + '\n\nnon_diegetic_music:\nFollow the authored music cues for these shots.')



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
    for row in rows:
        # Six-field H3 text ends with the music block; the old "last source
        # line" fallback incorrectly carried its music template into the next
        # scene as actor history. Let the current shot and image guide lead.
        row.update(song_seconds=duration,segment_count=len(rows),fixed_reference_settings='')
    return {'title':title[:120],'duration':duration,'segments':rows,'shared_setup':''}
