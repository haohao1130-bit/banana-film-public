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
from html import unescape
import re

from banana_mv.core import FPS
from banana_mv.film_actor_state import (
    WARDROBE_KINDS, _opening_actor_state, _advance_actor_state, _actor_state_lines,
    _current_appearance_anchor, _fixed_reference_with_python_priority,
)
from banana_mv.timed_slots import allocate_timed_chapters, parse_timed_source

CLIP = re.compile(
    r'(?im)^[ \t]*===\s*CLIP\s+([1-9]\d*)\s*'
    r'\(\s*(\d+(?:\.\d+)?)\s*s(?:ec(?:onds?)?)?\s*\)\s*===\s*$'
)
CLIP_LIKE = re.compile(r'(?im)^[ \t]*===\s*CLIP\b')


MASTER_SEGMENT = re.compile(
    r'(?im)^[ \t]*SEGMENT[ \t]+(\d+)[ \t]*\n(?:[ \t]*\n)*[ \t]*GLOBAL TIME[^\n]*\n(?:[ \t]*\n)*'
    r'[ \t]*LOCAL TIME[ \t]+00:00(?:\.000)?[ \t]*[-–—][ \t]*(\d+):(\d+(?:\.\d+)?)[ \t]*$')
MASTER_FIELDS = re.compile(
    r'(?m)^(subject_definitions|summary|retention_analysis|detailed_description|overall_soundscape|non_diegetic_music):[ \t]*$')


INLINE_SEGMENT = re.compile(
    r'(?im)^[ \t]*SEGMENT[ \t]+(\d+)[ \t]*[｜|:：][ \t]*'
    r'(\d+:\d{2}(?:\.\d+)?)[ \t]*[-–—~～至][ \t]*(\d+:\d{2}(?:\.\d+)?)[ \t]*$')


def _split_inline_segments(source):
    segments = list(INLINE_SEGMENT.finditer(source))
    if not segments:
        return None

    def seconds(clock):
        minutes, rest = clock.split(':')
        return int(minutes)*60 + float(rest)

    fixed = re.split(r'(?m)^[ \t]*(?:故事核心|劇情分段)[ \t]*[：:]?[ \t]*$',
                     source[:segments[0].start()], maxsplit=1)[0].strip()
    appendix = list(re.finditer(
        r'(?m)^[ \t]*【?(電影導演控制|電影攝影控制|角色動作與物理控制|角色表演控制|角色與物件連續性|角色語音控制|聲音與語音控制|背景音樂與音效|跨段連續性控制|生成優先級|全片限制|核心敘事)】?[ \t]*[：:]?[ \t]*$',
        source[segments[-1].end():]))
    tail = source[segments[-1].end():]
    end = segments[-1].end()+appendix[0].start() if appendix else len(source)
    controls = {match[1]: tail[match.end():appendix[i+1].start() if i+1<len(appendix) else len(tail)].strip()
                for i,match in enumerate(appendix)}
    voice = controls.get('聲音與語音控制', controls.get('角色語音控制', ''))
    music = controls.get('背景音樂與音效', '')
    cue_pattern = r'(?im)^[ \t]*SEGMENT[ \t]+0*(\d+)[：:]([^\n]+)$'
    notes = dict(re.findall(cue_pattern, music))
    music = re.sub(cue_pattern, '', music).strip()
    clips = []
    previous = 0.0
    for i, segment in enumerate(segments):
        start, stop = map(seconds, segment.group(2,3))
        if int(segment[1]) != i+1 or abs(start-previous)>1e-6 or stop<=start:
            raise ValueError('SEGMENT 時間碼必須從零開始，依序連號並連續。')
        body = source[segment.end():segments[i+1].start() if i+1<len(segments) else end].strip()
        if not body:
            raise ValueError(f'SEGMENT {i+1:02d} 缺少演出內容。')
        body = re.sub(r'\(S(\d+)\)[ \t]*「([^」]+)」',
                      lambda match: f'(S{match[1]}) <d>[Chinese] {match[2].strip()}</d>', body)
        if not re.match(r'^\[Shot 1\]', body):
            body = '[Shot 1]\n'+body
        clips.append((stop-start, '\n\n'.join((
            'subject_definitions:\n'+(fixed or 'Preserve the provided character references.'),
            f'summary:\nFilm only the assigned events in {stop-start:g} seconds.',
            'retention_analysis:\nPreserve the fixed characters, voices, appearance and location.',
            'detailed_description:\n'+body,
            'overall_soundscape:\nKeep dialogue synchronized.\n'+voice,
            'non_diegetic_music:\n'+'\n'.join(filter(None, (music, notes.get(str(i+1),'').strip()))) or 'non_diegetic_music:\nFollow local sound cues.'
        ))))
        previous = stop
    return clips


def split_segment_master(source):
    """Compile authored local timelines without repartitioning dialogue."""
    source = source.replace('\r\n', '\n').replace('\r', '\n')
    source = re.sub(r'\\[ \t]*$', '', source, flags=re.M)
    source = unescape(source).replace(r'\_', '_')
    source = re.sub(r'(?im)^([ \t]*SEGMENT[ \t]+\d+)[ \t]+(GLOBAL TIME[^\n]*?)[ \t]+(LOCAL TIME\b)', r'\1\n\2\n\3', source)
    fields = list(MASTER_FIELDS.finditer(source))
    sections = {field[1]: source[field.end():fields[i+1].start() if i+1<len(fields)
                                else len(source)].strip()
                for i,field in enumerate(fields)}
    detail = sections.get('detailed_description','')
    segments = list(MASTER_SEGMENT.finditer(detail))
    if not segments:
        if re.search(r'(?im)^\s*SEGMENT[ \t]+\d+[ \t]*\n(?:[ \t]*\n)*[ \t]*GLOBAL TIME', source):
            raise ValueError('已找到 SEGMENT 時間軸，但無法讀取分段。請保留 detailed_description、GLOBAL TIME 與 LOCAL TIME。')
        return _split_inline_segments(source)
    prelude = detail[:segments[0].start()].strip()
    retention = '\n'.join(line for line in sections.get('retention_analysis','').splitlines()
                          if not re.search(r'\bsegment\s+\d+|develops continuously from', line, re.I)).strip()
    clips = []
    for i, segment in enumerate(segments):
        if int(segment[1]) != i+1:
            raise ValueError('SEGMENT 必須從 1 開始依序連號。')
        seconds = int(segment[2])*60 + float(segment[3])
        stop = segments[i+1].start() if i+1<len(segments) else len(detail)
        body = detail[segment.end():stop].strip()
        body = re.sub(r'(?m)^([^\n]*?\(S\d+\)[^\n]*?:[ \t]*)(\[Chinese\][ \t]+[^\n]+)$',
                      r'\1<d>\2</d>', body)
        if '[Shot 1]' not in body:
            raise ValueError(f'SEGMENT {i+1:02d} 缺少 [Shot 1]。')
        clips.append((seconds, '\n\n'.join((
            'subject_definitions:\n' + '\n\n'.join(filter(None, (sections.get('subject_definitions'), prelude))),
            f'summary:\nFilm only the assigned shots in {seconds:g} seconds. Preserve the local speech and silence timings.',
            'retention_analysis:\n' + (retention or 'Preserve established identities and appearances.'),
            'detailed_description:\n' + body,
            'overall_soundscape:\nFollow local sound cues. ' + sections.get('overall_soundscape','').split('\n\n')[0],
            'non_diegetic_music:\nFollow local music cues and continue any established score.',
        ))))
    return clips


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


def _opening_wardrobe_indices(lines):
    """Retain only the source's explicitly authored opening clothing list.

    Film's fixed-setup filter previously discarded this list before Python Slot
    could initialize its proven garment state. Never infer wardrobe from camera
    notes, later SHOTs or the reference image.
    """
    selected=set()
    inside=False
    for i, raw in enumerate(lines):
        line=raw.strip()
        if re.match(r'^(?:開場穿著|初始穿著|初始服裝|開場服裝)\s*[：:]', line):
            selected.add(i)
            inside=True
        elif inside and line and any(pattern.search(line) for _,pattern in WARDROBE_KINDS):
            selected.add(i)
        else:
            inside=False
    return selected



def _unfinished_spoken_line(action):
    """Identify a dangling dialogue fragment by its final ellipsis."""
    spoken=list(re.finditer(
        r'\((S\d+)\)\s*(?:<d>(?:\[[^\]]+\])?\s*([^<]*)</d>|[「『]([^」』]*)[」』])',
        action))
    if not spoken:
        return ''
    last=spoken[-1]
    wording=(last.group(2) or last.group(3) or '').strip()
    return last.group(1) if re.search(r'(?:…{1,}|\.{3,}|—{2,})\s*$',wording) else ''


def _join_unfinished_dialogue(actions):
    """Keep one speaker's broken phrase and short breath in a single clip.

    Never invent or rewrite the lines. The source may contain multiple <d>
    tags, but Python must not separate them across generation windows.
    """
    result=[]
    i=0
    while i<len(actions):
        speaker=_unfinished_spoken_line(actions[i])
        end=-1
        if speaker:
            for k in range(i+1,min(i+5,len(actions))):
                line=actions[k]
                incoming=re.findall(r'\((S\d+)\)\s*(?:<d>|[「『])',line)
                if incoming:
                    if incoming[0]==speaker:
                        end=k
                    break
                if re.search(r'(?:鏡頭|攝影機|切至|換景|SHOT\s*\d+)',line,re.I):
                    break
        if end>i:
            result.append('\n'.join(actions[i:end+1]))
            i=end+1
        else:
            result.append(actions[i])
            i+=1
    return result



# Editorial timing guidance for native H3, not a promise of exact speech speed.
# Unlike the older allocator, count only the spoken text, not <d> markup.
# Keep this light: most silent camera/blocking cues happen while someone speaks.
FILM_DIALOGUE_TAIL_SECONDS = 0.65
FILM_CHAIN5_OPENING_SECONDS = 0.35


def _dialogue_budget_seconds(action):
    """Estimate on-screen speech time without an extra model or ASR runtime.

    Taiwanese Mandarin words plus breath/ellipsis pauses are budgeted before
    choosing the H3 duration. Stage direction is allowed to overlap dialogue.
    This is a conservative planning estimate, not speech recognition.
    """
    spoken=list(re.finditer(
        r'\(S\d+\)[^\n<「『]*?\s*(?:<d>(?:\[[^\]]+\])?\s*([^<]*)</d>|[「『]([^」』]*)[」』])',
        action))
    if spoken:
        seconds=0.0
        for match in spoken:
            words=(match.group(1) or match.group(2) or '').strip()
            chinese=sum('\u4e00'<=char<='\u9fff' for char in words)
            latin=len(re.findall(r'[A-Za-z]+|\d+',words))
            ellipses=len(re.findall(r'…+|\.{3,}|—{2,}',words))
            seconds+=(0.18 + 0.15*chinese + 0.35*latin
                      + 0.22*ellipses
                      + 0.11*sum(char in '，,、' for char in words)
                      + 0.06*sum(char in '？?!！' for char in words))
        # Voice and staging overlap; explicit breath/silence does not.
        for line in action.splitlines():
            if re.search(r'\(S\d+\)[^\n<「『]*?\s*(?:<d>|[「『])',line):
                continue
            if re.search(r'沉默半秒',line):
                seconds+=0.40
            elif re.search(r'吸氣|深呼吸|短暫停頓|片刻停頓',line):
                seconds+=0.20
            elif re.search(r'沉默片刻',line):
                seconds+=0.20
        return seconds
    if re.search(r'沉默半秒',action):
        return 0.40
    if re.search(r'短暫停頓|片刻停頓|短暫吸氣',action):
        return 0.20
    if re.search(r'深吸一口氣|深深吸氣',action):
        return 0.25
    # Short visual cue; acting/camera work can overlap with the dialogue.
    return 0.035


def _speech_safe_storyboard(chapters, fixed, total_seconds, ceiling, count, *, chain5=False, soundscape=''):
    """Fit complete authored action/dialogue units to native H3 frame windows.

    A generation clip is not an authored SHOT: editorial SHOTs may cross clip
    boundaries, but spoken sentences and their speaker cues never do. The source
    times guide pacing instead of imposing hard cut points inside a line.
    """
    atoms = []
    for chapter_index, chapter in enumerate(chapters):
        actions = _join_unfinished_dialogue(
            _compact_film_micro_beats(
                _shot_action_units("\n".join(chapter['actions']))))
        if not actions:
            continue
        budgets = [_dialogue_budget_seconds(action) for action in actions]
        # Proxy weights place scene actions approximately on the authored SHOT
        # timeline; the actual budgets below decide if a clip can fit.
        weights = [max(0.42, budget) for budget in budgets]
        elapsed = 0.0
        for action, weight, budget in zip(actions, weights, budgets):
            elapsed += weight
            atoms.append({'chapter': chapter_index, 'text': action, 'weight': weight,
                          'budget': budget,
                          'speaks': bool(re.search(r'\(S\d+\)[^\n<「『]*?(?:<d>|[「『])', action)),
                          'speaker': re.findall(r'\(S\d+\)', action)[-1:] or [],
                          'source_end': chapter['start'] + (chapter['end']-chapter['start'])
                          * elapsed / sum(weights)})
    if len(atoms) < count:
        raise ValueError('原始 SHOT 無足夠的完整事件切點；請減少分段數或延長片長上限。')

    # The 10-second selector is a CEILING, not a fixed clip duration and
    # definitely not a fixed number of segments. First try the original number
    # of legal H3 clips. If a sentence will run into the cut, end the preceding
    # clip before that sentence and move the intact performance to the next.
    # When the original number of slots cannot accommodate all completed
    # speech, retry with one more (shorter) legal slot instead of rejecting.
    # Frame grid, entire story duration and prompt order remain unchanged.
    maximum = 5 + 17 * ((math.floor(ceiling * FPS) - 5) // 17)
    target = round(total_seconds * FPS)
    last_allowed_count = min(
        len(atoms), math.floor((target + 1.5 * FPS) / 124))
    if last_allowed_count < count:
        raise ValueError('整片時長無法排入 H3 最短合法鏡頭。')

    cumulative_budget = [0.0]
    cumulative_speakers = [0]
    for atom in atoms:
        cumulative_budget.append(cumulative_budget[-1] + atom['budget'])
        cumulative_speakers.append(cumulative_speakers[-1] + int(atom['speaks']))

    selected = None
    for slot_count in range(count, last_allowed_count + 1):
        # Prefer 7–10 seconds, but allow native 5.167–6.583-second shots
        # only when necessary to keep every spoken phrase intact.
        minimum = (175 if ceiling >= 10 and slot_count * 175 <= target
                   else 124)
        choices = list(range(minimum, maximum + 1, 17))
        if not choices:
            break
        states = {(0, 0): (0.0, [])}  # (delivered frames, action cursor)
        for slot_no in range(1, slot_count + 1):
            following = {}
            for (used, cursor), (cost, path) in states.items():
                for frames in choices:
                    if chain5 and slot_no > 1 and frames + 17 > maximum:
                        continue
                    new_used = used + frames
                    remaining = slot_count - slot_no
                    if (new_used + remaining * minimum > target + 1.5 * FPS
                        or new_used + remaining * maximum < target - 1.5 * FPS):
                        continue
                    last_slot = slot_no == slot_count
                    if last_slot:
                        stops = [len(atoms)]
                    else:
                        # Bound the DP search near the authored timeline but
                        # allow cutting *earlier* before a full next utterance.
                        stops = (
                            boundary for boundary in
                            range(cursor + 1, len(atoms) - remaining + 1)
                            if abs(atoms[boundary-1]['source_end'] -
                                   new_used / FPS) <= 6.0)
                    for stop in stops:
                        if stop <= cursor:
                            continue
                        speech_present = (
                            cumulative_speakers[stop] >
                            cumulative_speakers[cursor])
                        safe_capacity = frames / FPS
                        if speech_present:
                            safe_capacity -= FILM_DIALOGUE_TAIL_SECONDS
                            safe_capacity -= (FILM_CHAIN5_OPENING_SECONDS
                                              if slot_no > 1 else 0.18)
                        speech_seconds = (
                            cumulative_budget[stop] -
                            cumulative_budget[cursor])
                        # NO hard timing boundary through a dialogue unit:
                        # move that whole unit to the following clip.
                        if speech_seconds > safe_capacity + 1e-8:
                            continue
                        spare = safe_capacity - speech_seconds
                        if last_slot:
                            delta = new_used / FPS - total_seconds
                            extra = delta * delta * 35.0
                        else:
                            before, after = atoms[stop-1], atoms[stop]
                            delta = new_used / FPS - before['source_end']
                            same_shot = before['chapter'] == after['chapter']
                            same_voice = bool(
                                before['speaker'] and
                                before['speaker'] == after['speaker'])
                            extra = delta * delta * 1.3
                            extra += 0.45 if same_shot else 0.0
                            if same_shot and same_voice:
                                extra += 0.65
                        if speech_present:
                            extra += max(0.0, 0.35-spare)**2 * 12.0
                        key = (new_used, stop)
                        value = cost + extra
                        if key not in following or value < following[key][0]:
                            following[key] = (
                                value, path + [(frames, stop)])
            if not following:
                break  # Try an additional shorter native H3 clip.
            states = following
        else:
            valid = [
                (key, value) for key, value in states.items()
                if key[1] == len(atoms) and
                abs(key[0] - target) <= 1.5 * FPS]
            if valid:
                _, (score, selected) = min(
                    valid, key=lambda row: (
                        abs(row[0][0]-target) * 100 + row[1][0],
                        abs(row[0][0]-target)))
                break
    if selected is None:
        raise ValueError(
            '已嘗試提前收鏡並把完整台詞移到下一段，但在全片秒數及 '
            'H3 合法影格限制下仍無法容納全部對白。請增加全片長度；'
            '程式不會裁字或重複台詞。')

    state = _opening_actor_state(fixed, chapters)
    delivered = []
    cursor = 0
    for frames, stop in selected:
        length = frames / FPS
        allocated = atoms[cursor:stop]
        total_weight = sum(atom['weight'] for atom in allocated)
        fragments = []
        used_weight = 0.0
        position = 0
        while position < len(allocated):
            chapter_index = allocated[position]['chapter']
            end = position + 1
            while end < len(allocated) and allocated[end]['chapter'] == chapter_index:
                end += 1
            group = allocated[position:end]
            chapter = chapters[chapter_index]
            begin_seconds = used_weight / total_weight * length
            used_weight += sum(atom['weight'] for atom in group)
            end_seconds = used_weight / total_weight * length
            performance = '\n'.join(atom['text'] for atom in group)
            constraints = chapter.get('constraints') or []
            fragments.append(
                f'USER-SPECIFIED FILM TIME — this chapter is assigned to '
                f'{chapter["start"]:.3f}–{chapter["end"]:.3f}s source time; '
                f'its active time inside THIS clip is {begin_seconds:.3f}–{end_seconds:.3f}s. '
                'Follow its action order; do not film future chapters early.\n'
                + performance
                + ('\nConstraints for THIS chapter only (not extra events):\n'
                   + '\n'.join('- ' + note for note in constraints) if constraints else ''))
            position = end
        prompt = '\n\n'.join(fragments)
        delivered.append((length, compile_storyboard_slot(fixed, prompt, length, length, state, soundscape=soundscape)))
        cursor = stop
    if cursor != len(atoms):
        raise ValueError('有劇情事件未分配到攝影段落。')
    return delivered


def protect_chain5_opening(prompt):
    """Reserve a visual-only lead-in before the five discarded context frames.

    Prompt steering is best-effort for a joint A/V model; it cannot guarantee
    speech-free audio by itself. Keep the instruction within the first shot.
    """
    marker = 'CHAIN5_VISUAL_ONLY_LEAD_IN'
    if marker in prompt:
        return prompt
    shot = re.search(r'\[Shot 1\](?!\s*At\b)', prompt)
    if not shot:
        return prompt
    lead = (' CHAIN5_VISUAL_ONLY_LEAD_IN: For the first 0.35 seconds, silently '
            'continue the preceding motion, gaze and expression; no new dialogue, '
            'no vocal onset and no new sound cue. Only after this visual-only '
            'lead-in does the first spoken line and its synced mouth motion begin.\n')
    return prompt[:shot.end()] + lead + prompt[shot.end():]


# Classic Python Slot handoff model: reference/world settings are immutable
# shared_setup, whereas plot actions are assigned ONCE to isolated clip orders.
# Do not mistake the first global paragraph for the opening filmed event.
_FILM_SHARED_HEADING = re.compile(
    r'^\s*(?:#{1,6}\s*)?(?:【)?(?:共同設定|共通設定|共用設定|全局設定|'
    r'全域設定|固定設定|全片固定設定|角色設定|人物設定|角色綁定|'
    r'世界觀|場景設定|全局電影設定|電影設定|[Ss]hared [Ss]ettings|[Cc]ommon [Ss]ettings|subject_definitions)(?:】)?\s*[：:]?\s*$')
_FILM_STORY_HEADING = re.compile(
    r'^\s*(?:#{1,6}\s*)?(?:【)?(?:故事內容|故事劇情|劇情內容|'
    r'劇本內容|故事大綱|劇情大綱|故事分段|劇情分段|'
    r'分鏡時間軸|分鏡腳本|分鏡內容|拍攝段落|'
    r'段落安排|演出內容|故事開始|正片內容|精密鏡頭時間軸|鏡頭時間軸|[Ss]hot [Tt]imeline|[Ss]toryboard|detailed_description)(?:】)?\s*[：:]?\s*$')
_FILM_EVENT_HEADING = re.compile(
    r'^\s*(?:#{1,6}\s*)?(?:第[一二三四五六七八九十百零〇\d]+[幕段場鏡]'
    r'(?:\s*[｜|:：\-—].*)?|(?:ACT|SCENE|SHOT)\s*\d+'
    r'(?:\s*[｜|:：\-—].*)?)\s*$',
    re.I)
_FILM_FIXED_BLOCK_START = 'FIXED_REFERENCE_SETTINGS (shared across ALL clips; not a filmed event):'
_FILM_LOCAL_BLOCK_START = 'CURRENT_CLIP_COMMISSION (only these events are performed now):'


def _split_film_shared_source(source):
    """Return unchanged fixed setup and ordered story, like Classic split_source.

    Require an actual narrative heading or chapter before separating source.
    Without that boundary, leave the input untouched; never guess that the
    opening narrative is a fixed rule or that a future event is global.
    """
    lines = source.replace('\r\n', '\n').splitlines()
    first_story = None
    strip_heading = False
    for i, line in enumerate(lines):
        if _FILM_STORY_HEADING.fullmatch(line) or _FILM_STORY_NUMBERED.match(line):
            first_story = i
            strip_heading = True
            break
        if _FILM_EVENT_HEADING.fullmatch(line):
            first_story = i
            break
    if first_story is None or first_story == 0:
        return '', source
    # Like Classic's setup/story split: keep the *setting* section, not a
    # leading premise or overview which may reveal a later outcome. Start at
    # the first explicitly marked shared/role section in the prelude.
    starts = [i for i, line in enumerate(lines[:first_story])
              if _FILM_SHARED_HEADING.fullmatch(line) or _FILM_FIXED_NUMBERED.match(line)]
    if not starts:
        return '', source
    explicit_common = next((i for i in starts if re.match(
        r'^\s*(?:#{1,6}\s*)?(?:【)?(?:共同設定|共通設定|共用設定|全局設定|全域設定|固定設定|全片固定設定)',
        lines[i])), None)
    start_at = explicit_common if explicit_common is not None else starts[0]
    common = '\n'.join(lines[start_at:first_story]).strip()
    narrative = '\n'.join(lines[first_story + int(strip_heading):]).strip()
    return (common, narrative) if narrative else ('', source)


def _split_film_handoff(prompt):
    """Read the fixed setting block from a separately commissioned clip."""
    if not prompt.startswith(_FILM_FIXED_BLOCK_START + '\n'):
        return '', prompt
    pivot='\n\n' + _FILM_LOCAL_BLOCK_START + '\n'
    fixed, sep, local=prompt[len(_FILM_FIXED_BLOCK_START)+1:].partition(pivot)
    return (fixed.strip(), local) if sep else ('',prompt)



# Match the authored SHOT time ruler as well as the common "SHOT 01 | 0-5秒"
# form. H3 style sub-camera headings SHOT 11A/B/C belong to parent SHOT 11.
_FILM_SHOT_HEADER = re.compile(
    r'(?im)^[ \t]*(?:#{1,6}[ \t]+)?SHOT[ \t]+(\d+)(?![A-Za-z0-9])'
    r'[ \t]*[｜|:：][ \t]*((?:\d+:[0-5]\d|\d+)(?:\.\d+)?)[ \t]*[-–—~～至][ \t]*'
    r'((?:\d+:[0-5]\d|\d+)(?:\.\d+)?)(?![\d.:])(?:[ \t]*(?:秒(?:鐘)?|s(?:ec)?\b))?[^\n]*$'
)
def parse_shot_time(value):
    minutes, colon, seconds = value.rpartition(':')
    return int(minutes) * 60 + float(seconds) if colon else float(seconds)


_FILM_MICRO_RANGE = re.compile(
    r'^\s*\d+(?:\.\d+)?\s*[-–—~～至]\s*\d+(?:\.\d+)?\s*(?:秒)?\s*$')
_FILM_FIXED_NUMBERED = re.compile(
    r'^\s*[一二三四五六七八九十百零〇\d]+[、.．]\s*'
    r'(?:角色|人物|身份|身分|場景|攝影|聲音|演技|固定|共用|共同|全局|全域)')
_FILM_STORY_NUMBERED = re.compile(
    r'^\s*[一二三四五六七八九十百零〇\d]+[、.．]\s*'
    r'(?:精密鏡頭時間軸|鏡頭時間軸|劇情|故事|分鏡|正片)')
_FILM_METADATA = re.compile(
    r'^\s*(?:影片類型|畫面比例|影格率|對白語言|對白模式|整體影像|'
    r'影片風格|固定角色|人物外貌|角色綁定|世界觀|背景設定|演出風格)\s*[：:]')
_FILM_FUTURE_SETUP = re.compile(
    r'第一次落淚發生於SHOT|說出「[^」]*」時|最後耳光前|'
    r'耳光慢動作開始時|三角度重播期間|最後一句台詞說完')
_FILM_END_APPENDIX = re.compile(
    r'(?m)^[ \t]*(?:[一二三四五六七八九十]+[、.．][ \t]*)?【?'
    r'(最終生成優先級|禁止與連續性檢查|聲音與表演控制|電影攝影控制|核心敘事|'
    r'空拍攝影控制|臉部修復測試控制|人物動作控制|聲音設定|畫面限制|核心測試)'
    r'】?[ \t]*[:：]?[ \t]*$')



def _film_shared_before_shots(source):
    """Classic-style fixed work order, from an *authored* common source.

    Include complete marked cast/world/sound blocks and introductory technical
    metadata. Never smuggle the 'story core' synopsis or a later plot outcome
    into every clip; future scene-local cues stay with the scene.
    """
    fixed=[]
    mode='intro'
    for raw in source.replace('\r\n','\n').splitlines():
        line=raw.strip()
        if not line:
            continue
        if line in ('故事核心','故事概念','劇情核心','故事簡介'):
            mode='synopsis'
            continue
        if _FILM_STORY_NUMBERED.match(line) or _FILM_STORY_HEADING.fullmatch(line):
            mode='story'
            continue
        if _FILM_FIXED_NUMBERED.match(line) or _FILM_SHARED_HEADING.fullmatch(line) or line in ('【固定角色】', '【固定場景】'):
            mode='fixed'
            fixed.append(raw)
            continue
        if mode=='fixed':
            if not _FILM_FUTURE_SETUP.search(line):
                fixed.append(raw)
        elif mode=='intro' and (_FILM_METADATA.match(line) or re.match(
            r'^\s*(?:@圖片\d+|<Picture\s+\d+>|\(S\d+\)\s*=|全片使用)',line)):
            fixed.append(raw)
    return '\n'.join(fixed).strip()


def _compact_film_micro_beats(actions):
    """Keep timestamped dialogue, its breath, and its visible acting as a unit.

    Source scripts often have 5-15 sub-second ranges in one SHOT. Dividing
    each raw line instead of each authored beat causes the last word to migrate
    into the wrong clip and blows up the DP search.
    """
    if not any(_FILM_MICRO_RANGE.fullmatch(line.strip()) for line in actions):
        return actions
    groups=[]
    current=[]
    for line in actions:
        if _FILM_MICRO_RANGE.fullmatch(line.strip()) and current:
            groups.append('\n'.join(current))
            current=[line]
        else:
            current.append(line)
    if current:
        groups.append('\n'.join(current))
    return groups


def _native_master_storyboard(source):
    """Adapt a timed six-field H3 master to the existing shot planner."""
    source = re.sub(r'\\(?=[<>]|[ \t]*$)', '', source, flags=re.M)
    fields = list(re.finditer(r'(?m)^(subject_definitions|summary|retention_analysis|detailed_description|overall_soundscape|non_diegetic_music):[ \t]*$', source))
    sections = {m[1]: source[m.end():fields[i+1].start() if i+1<len(fields) else len(source)].strip()
                for i,m in enumerate(fields)}
    detail = sections.get('detailed_description', '')
    shots = list(re.finditer(
        r'(?m)^\[Shot[ \t]+\d+\][ \t]*\n'
        r'(?:At[ \t]+)?(\d+:\d+(?:\.\d+)?)(?:[ \t]*[-–—~至][ \t]*(\d+:\d+(?:\.\d+)?)[ \t]*$|(?=,))', detail))
    if not shots:
        return source
    def seconds(clock):
        minutes, value = clock.split(':')
        return int(minutes)*60+float(value)
    prelude = detail[:shots[0].start()].split('\nSEGMENT ',1)[0].strip()
    # Only stable production instructions belong in every work order.
    prelude = '\n'.join(line for line in prelude.splitlines()
                        if not re.search(r'briefly regains|first tear falls', line, re.I))
    fixed = '\n'.join(filter(None, (sections.get('subject_definitions'),
                                   sections.get('retention_analysis'), prelude)))
    for section, label in (('overall_soundscape', '聲音設定'), ('non_diegetic_music', '背景使用')):
        first = sections.get(section, '').split('. ', 1)[0].strip()
        if first:
            fixed += f'\n{label}：{first.rstrip(".")}.'
    rows = ['共同設定', fixed, '分鏡時間軸']
    for i, shot in enumerate(shots):
        end = shots[i+1].start() if i+1<len(shots) else len(detail)
        body = re.split(r'(?m)^SEGMENT[ \t]+[A-Z]\b', detail[shot.end():end], maxsplit=1)[0].strip()
        body = re.sub(r'(?m)^\d+:\d+(?:\.\d+)?\s*[-–—~至]\s*\d+:\d+(?:\.\d+)?:?[ \t]*$', '', body)
        body = body.lstrip(', ')
        stop = shot[2] or (shots[i+1][1] if i+1<len(shots) else None)
        if stop is None:
            spans = re.findall(r'(?m)^\d+:\d+(?:\.\d+)?\s*[-–—~至]\s*(\d+:\d+(?:\.\d+)?):', detail[shot.end():end])
            if not spans:
                return source
            stop = spans[-1]
        rows.extend((f'SHOT {i+1:02d}｜{seconds(shot[1]):g}–{seconds(stop):g}秒', body))
    return '\n'.join(rows)


def distribute_manual_prompt(clips, total_seconds, ceiling, *, chain5=False):
    """Split an unmarked long prompt at its existing paragraph or sentence boundaries."""
    if len(clips) != 1:
        return clips
    _, source = clips[0]
    source = _native_master_storyboard(source)
    shared_setup, story = _split_film_shared_source(source)
    # A SHOT-timed script will also get its shared setup in
    # subject_definitions. For unheaded chapter scripts, never split common
    # identities, speaker mappings or the fixed world into the first clip.
    if shared_setup:
        source = story
    largest = max(range(124, math.floor(ceiling * FPS) + 1, 17)) / FPS
    count = math.ceil(total_seconds / largest)
    shots = list(_FILM_SHOT_HEADER.finditer(source))
    soundscape = ''
    shared_controls = []
    if shots:
        setup = (shared_setup + '\n' + source[:shots[0].start()]
                 if shared_setup else source[:shots[0].start()])
        end = _FILM_END_APPENDIX.search(source[shots[-1].end():])
        body_end = shots[-1].end() + end.start() if end else len(source)
        appendix = source[body_end:]
        appendix_sections = list(_FILM_END_APPENDIX.finditer(appendix))
        for index, heading in enumerate(appendix_sections):
            stop = appendix_sections[index+1].start() if index+1<len(appendix_sections) else len(appendix)
            body = appendix[heading.end():stop].strip()
            if heading[1] == '聲音設定':
                soundscape = body
            elif heading[1] in ('人物動作控制', '畫面限制') and body:
                shared_controls.append(heading[0].strip() + '\n' + body)
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
            chapters.append({'start':parse_shot_time(shot[2]), 'end':parse_shot_time(shot[3]),
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
        longest = max(row['end'] for row in chapters)
        if shots and longest > total_seconds + 1e-8:
            raise ValueError(
                f'全片指定 {total_seconds:g} 秒，但最後 SHOT 延伸到 {longest:g} 秒；'
                '請先統一全片長度與 SHOT 時間軸。Python 不會截斷最後台詞。')
        if any(not 0 <= row['start'] < row['end'] for row in chapters):
            raise ValueError('鏡頭時間軸的結束時間必須大於起始時間。')
        setup_lines=setup.splitlines()
        opening_lines=_opening_wardrobe_indices(setup_lines)
        # SHOT stories use complete authored fixed blocks, not a whitelist
        # of isolated lines. The old whitelist removed most of the cast/world
        # settings and led to the first clip stealing the entire setup.
        fixed = (_film_shared_before_shots(setup) if shots else
                 shared_setup if shared_setup else '\n'.join(
                     line for index,line in enumerate(setup_lines)
                     if (index in opening_lines or re.match(
                         r'^\s*(?:主角|角色|人物(?:外貌|五官|身分|身份)|服裝(?:隨|依)|固定場景|影片風格|影像風格|場景|主要道具|聲音設定|以.+(?:背景音樂|環境音效)|全片無對白|無旁白|\\?<Picture\s+\d+>|[(]S[12][)]|16:9|冷調|遵守180|全片使用|對白必須|允許自然|背景使用|不加入|不擅自)', line))
                     and not re.search(r'最後才|結局|修復AI|修電腦', line)))
        # Global audio and continuity rules after the last SHOT remain
        # shared, but source-plot notes are never copied into every clip.
        if shared_setup:
            suffix = '\n'.join(
                line for line in setup_lines
                if line.strip().startswith(
                    ('全片使用', '對白必須', '允許自然', '背景使用', '全片無對白')))
            if suffix:
                fixed += '\n' + suffix
        if shots:
            fixed = '\n'.join(filter(None, [fixed, *shared_controls]))
            return _speech_safe_storyboard(chapters, fixed, total_seconds, ceiling, count, chain5=chain5, soundscape=soundscape)
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
        return [(length, '\n\n'.join(filter(None, [fixed, prompt])))
                for length, prompt in zip(lengths, prompts)]
    if total_seconds <= largest and not shared_setup:
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
    result=[]
    for i in range(count):
        local='\n'.join(units[cuts[i]:cuts[i+1]])
        if shared_setup:
            # Exactly the same fixed rules in every local shoot order;
            # local events only once, never a full-story preview.
            local=(_FILM_FIXED_BLOCK_START + '\n' + shared_setup
                   + '\n\n' + _FILM_LOCAL_BLOCK_START + '\n' + local)
        result.append((total_seconds / count, local))
    return result


def compile_storyboard_slot(fixed, prompt, length, source_length, state=None, *, soundscape=''):
    """Turn the MV allocator's local assignments into native Ref2VA fields."""
    assigned = re.compile(r'(?m)^USER-SPECIFIED FILM TIME [^\n]*?'
                          r'inside THIS clip is ([\d.]+)–[\d.]+s\.[^\n]*\n')
    matches = list(assigned.finditer(prompt))
    start_state={kind:item.copy() for kind,item in (state or {}).items()}
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
    if not shots:
        raise ValueError('這個生成窗只有已發生事項／攝影備註，沒有當段演出。請調整 SHOT 時間或加入明確動作。')
    details = '\n\n'.join(shots)
    # H3 jointly generates video and audio; a 17k+5 frame boundary is not
    # speech-aware. The final delivered frames must be a quiet acting beat.
    dialogue_end_note = (' All spoken lines must end at least '
        f'{FILM_DIALOGUE_TAIL_SECONDS:.2f} seconds before the clip ends; '
        'finish the last word and its trailing phoneme before then. '
        'Use the remaining end beat for silent acting and existing ambience, '
        'without another utterance or repeated words.'
        if re.search(r'<d>', details) else '')
    state_note = ''
    fixed_for_clip = fixed
    if start_state:
        # Mirror Classic Python Slot: tracked current appearance overrides
        # stale opening clothes, while untracked traits still use reference
        # photos. The first-shot note is a FACT, never a new undressing action.
        incoming=_actor_state_lines(start_state)
        outgoing=_actor_state_lines(state)
        state_note=(
            'CURRENT_ACTOR_STATE (at clip start; authoritative over initial wardrobe):\n'
            + incoming
            + '\nEXPECTED_ACTOR_STATE_AFTER_THIS_CLIP (only through assigned actions):\n'
            + outgoing
            + '\nPreserve reference identity. The current wardrobe is authoritative; '
              'never re-dress or replay previously completed wardrobe changes.')
        fixed_for_clip=_fixed_reference_with_python_priority(fixed, state_note)
        details=details.replace('[Shot 1] ', '[Shot 1] '
            + _current_appearance_anchor(start_state)
            + '\nContinue the assigned actions once from this state.\n', 1)
    refs = sorted(set(re.findall(r'<Picture (\d+)>', fixed + '\n' + details)), key=int)
    retention = '\n'.join(
        f'<Picture {ref}>: preserve referenced identity and stable features; '
        + ('apply the Python current wardrobe instead of the initial reference outfit.'
           if start_state else 'preserve the referenced appearance.')
        for ref in refs)
    subject=fixed_for_clip or 'Use the actors and scene specified in the shots.'
    if state_note: subject+='\n'+state_note
    music = ('No background music.' if re.search(r'無背景音樂|不加背景音樂', soundscape)
             else 'Follow the authored music cues for these shots.')
    return ('subject_definitions:\n' + subject
            + '\n\nsummary:\nFilm the assigned shots in order within '
            + f'{length:.3f} seconds. Only text enclosed in <d> is spoken dialogue; '
            + 'all other Chinese stage directions describe silent actions. Preserve speaker IDs.'
            + dialogue_end_note
            + '\n\nretention_analysis:\n' + (retention or 'Preserve established appearance and continuity.')
            + '\n\ndetailed_description:\n' + details
            + '\n\noverall_soundscape:\n' + (soundscape or 'Follow the specified voices, dialogue, and scene sounds.')
            + '\n\nnon_diegetic_music:\n' + music)



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
    shared_sources=[]
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
    ceiling=float(req['segment_seconds'])
    model_counts=[legal_frames(seconds,ceiling) for seconds,_ in clips]
    delivery_counts=model_counts
    if req.get('authored_segment_master'):
        from banana_mv.film_continuity import render_frames
        delivery_counts=[round(seconds*FPS) for seconds,_ in clips]
        model_counts=[render_frames(frames) if i and req.get('mode')=='chain5'
                      else 5+17*math.ceil((frames-5)/17)
                      for i,frames in enumerate(delivery_counts)]
    aligned_duration=sum(delivery_counts)/FPS
    if req.get('target_is_exact') and abs(aligned_duration-target)>tolerance + 1e-8:
        # Keep authored clip boundaries on the delivery timeline. The model
        # renders on its coarser grid and trim_native trims the excess.
        boundaries=[0]
        elapsed=0.0
        for seconds,_ in clips:
            elapsed+=seconds
            boundaries.append(round(elapsed*FPS))
        authored_counts=[end-start for start,end in zip(boundaries,boundaries[1:])]
        from banana_mv.film_continuity import render_frames
        required=[render_frames(frames) if i and req.get('mode')=='chain5'
                  else 5+17*math.ceil((frames-5)/17)
                  for i,frames in enumerate(authored_counts)]
        if max(required)<=math.floor(ceiling*FPS):
            delivery_counts=authored_counts
            model_counts=required
    for i,(seconds,text) in enumerate(clips):
        if not isinstance(text,str) or not text.strip():
            raise ValueError(f'第 {i+1} 段是空的。')
        mapped=normalize(map_mentions(req,text,image_count),image_count)
        # Every clip is a self-contained native H3 work order. For sectioned
        # plain-text source, retain a separately inspectable shared_setup too.
        # For already-compiled six-field H3 prompts, the complete reference
        # rules are already inside this clip's subject_definitions.
        fixed,_=_split_film_handoff(mapped)
        if not fixed and mapped.lstrip().startswith('subject_definitions:\n'):
            fixed=mapped.split('subject_definitions:\n',1)[1].split(
                '\n\nsummary:',1)[0].strip()
        shared_sources.append((fixed, mapped.startswith(_FILM_FIXED_BLOCK_START)))
        frames=delivery_counts[i]
        actual=frames/FPS
        validator(mapped,actual,req['sound_mode'])
        row={'index':i,'start_frame':frame_start,'frames':frames,
             'start':frame_start/FPS,'seconds':actual,'model_frames':model_counts[i],
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
    marked=[fixed for fixed,is_handoff in shared_sources if is_handoff]
    if marked and (len(marked)!=len(rows) or len(set(marked))!=1):
        raise ValueError('手動分段共同設定交接不完整或互相矛盾，請保留相同的固定設定。')
    common=marked[0] if marked else ''
    if not common and shared_sources:
        # Compiled SHOT work orders already embed the original fixed settings
        # in subject_definitions. Surface that same immutable identity/world
        # table as shared_setup rather than leaving the job-level field blank.
        # Local evolving wardrobe notes must stay specific to each slot.
        baseline=[fixed.split('\nCURRENT_ACTOR_STATE (',1)[0].strip()
                  for fixed,_ in shared_sources]
        if baseline[0] and len(set(baseline)) == 1:
            common=baseline[0]
    for row,(fixed,_) in zip(rows,shared_sources):
        # The fixed reference is a real per-slot work-order field, just like
        # Classic MV. Do NOT copy the previous clip's final source sentence as
        # a pseudo-state or add another performed event.
        row.update(song_seconds=duration,segment_count=len(rows),
                   fixed_reference_settings=fixed)
    return {'title':title[:120],'duration':duration,
            'segments':rows,'shared_setup':common}
