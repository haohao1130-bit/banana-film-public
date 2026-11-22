"""Read authored ACT timelines as isolated native MiniMax H3 film commissions.

The director route also accepts an explicit CLIP action/story timeline.
"""
import re

_ACT = re.compile(
    r'(?im)^[ \t]*ACT[ \t]+(?P<number>\d+)[ \t]*[｜|:：\-—][ \t]*'
    r'(?P<start>\d{1,2}:\d{2}(?:\.\d+)?)[ \t]*[-–—－~～至][ \t]*'
    r'(?P<end>\d{1,2}:\d{2}(?:\.\d+)?)[ \t]*$'
)
_ACT_LIKE = re.compile(r'(?im)^[ \t]*ACT[ \t]+\d+[ \t]*[｜|:：\-—][ \t]*\d')
_SHARED = re.compile(
    r'(?m)^[ \t]*【(?:共同設定|共通設定|共用設定|固定設定|全局設定|全域設定)】[^\n]*$'
)
_STORY_START = re.compile(r'(?m)^[ \t]*【(?:分段通告單|分段劇情|分鏡時間軸|故事內容)】[^\n]*$')
_BEAT = re.compile(
    r'(?m)^[ \t]*(?P<start>\d+(?:\.\d+)?)[ \t]*[-–—－~～至][ \t]*'
    r'(?P<end>\d+(?:\.\d+)?)[ \t]*秒[：:][ \t]*'
)
_QUOTE = re.compile(r'「([^」\n]+)」')
_SPEECH = re.compile(r'(?:說|問|喊|吼|道|答|回應|喝斥|咆哮)[：:]?[ \t]*$')
_BINDING = re.compile(r'@(?:圖片|图片|image)[ \t]*(\d+)[ \t]*[=＝][ \t]*([^，,：:\n\s]+)', re.I)
_FIELD = re.compile(r'(?m)^[ \t]*【([^】\n]+)】[ \t]*')
_COMPILER_META = re.compile(
    r'(?ms)^■[ \t]*(?:H3[ \t]*鏡頭指令|通告單格式)[^\n]*\n.*?(?=^■|\Z)'
)
_SOUND_QUOTE = re.compile(r'「(鏗|鏘|砰|轟|喀|咚|啪)」')
_CLIP_COMMISSION = re.compile(
    r'(?im)^[ \t]*===[ \t]*CLIP[ \t]+(\d+)[ \t]+(action|story)[ \t]*===[ \t]*$'
)
_CLIP_TIME = re.compile(
    r'^時間[：:][ \t]*(\d{1,2}:[0-5]\d(?:\.\d+)?)[ \t]*[-–—－~～至][ \t]*'
    r'(\d{1,2}:[0-5]\d(?:\.\d+)?)[ \t]*$'
)
_CLIP_HEADER = re.compile(r'(?im)^[ \t]*===[ \t]*CLIP\b')


def _clock(value):
    minutes, seconds = value.split(':', 1)
    return int(minutes) * 60 + float(seconds)


def split_clip_commissions(story, default_seconds):
    """Keep each authored CLIP body and read its delivery window."""
    source = story.replace('\r\n', '\n').replace('\r', '\n')
    markers = list(_CLIP_COMMISSION.finditer(source))
    if not markers:
        return None
    if len(_CLIP_HEADER.findall(source)) != len(markers):
        raise ValueError('CLIP 通告單標記需為 === CLIP 0 action === 或 === CLIP 0 story ===。')
    first = int(markers[0][1])
    if first not in (0, 1):
        raise ValueError('CLIP 通告單必須從 0 或 1 開始連號。')
    shared = source[:markers[0].start()].strip()
    shared = re.sub(r'(?im)^[ \t]*(?:===[ \t]*SETUP[ \t]*===|subject_definitions:)[ \t]*\n', '', shared)
    clips = []
    previous = 0.0
    for i, marker in enumerate(markers):
        number = int(marker[1])
        if number != first + i:
            raise ValueError('CLIP 通告單編號必須連續。')
        stop = markers[i+1].start() if i+1 < len(markers) else len(source)
        body = source[marker.end():stop].strip()
        body = re.sub(r'(?im)^[ \t]*===[ \t]*END[ \t]*===[ \t]*\Z', '', body).strip()
        first_line, _, local = body.partition('\n')
        seconds = default_seconds
        if re.match(r'^時間[：:]', first_line):
            timing = _CLIP_TIME.fullmatch(first_line)
            if not timing:
                raise ValueError(f'CLIP {number} 時間格式需為「時間：00:00–00:10」。')
            start, end = map(_clock, timing.groups())
            if abs(start - previous) > 0.01 or end <= start:
                raise ValueError(f'CLIP {number} 時間必須接續前段且不得重疊。')
            seconds = end - start
            body = local.strip()
        if not body:
            raise ValueError(f'CLIP {number} 沒有當段內容。')
        clips.append((seconds, marker[2].lower(), body))
        previous += seconds
    return shared.strip(), clips


def _field(body, name):
    matches = list(_FIELD.finditer(body))
    for i, match in enumerate(matches):
        if match.group(1).strip() == name:
            stop = matches[i + 1].start() if i + 1 < len(matches) else len(body)
            return body[match.end():stop].strip()
    return ''


def _inline(body, name):
    found = re.search(rf'(?m)^[ \t]*{re.escape(name)}[：:][ \t]*(.*)$', body)
    return found.group(1).strip() if found else ''


def _stamp(seconds):
    millis = round(seconds * 1000)
    minutes, remain = divmod(millis, 60000)
    whole, milli = divmod(remain, 1000)
    return f'{minutes:02d}:{whole:02d}.{milli:03d}'


def _tag_speech(line, cast):
    """Mark only explicitly authored character speech.

    A shot can introduce an actor by name and refer to the same speaker as
    '他' after a semicolon. Resolve this within the current shot only.
    Quoted props and onomatopoeia are not dialogue.
    """
    out = []
    cursor = 0
    prior_quote_end = 0
    for quote in _QUOTE.finditer(line):
        out.append(line[cursor:quote.start()])
        before = line[prior_quote_end:quote.start()]
        phrase = before.rsplit('。', 1)[-1].rsplit('；', 1)[-1]
        if _SPEECH.search(phrase):
            candidates = []
            for window in (phrase, line[:quote.start()]):
                candidates = []
                for number, name in cast.items():
                    for token in (name, f'@圖片{number}', f'<Picture {number}>'):
                        at = window.rfind(token)
                        if at >= 0:
                            candidates.append((at, number))
                horse = window.rfind('赤兔馬')
                if horse >= 0:
                    candidates.append((horse, max(cast) + 1))
                if candidates:
                    break
            if candidates:
                speaker = max(candidates)[1]
                out.append(f'(S{speaker}) <d>[Chinese] {quote.group(1)}</d>')
            else:
                out.append(quote.group(0))
        else:
            out.append(quote.group(0))
        cursor = quote.end()
        prior_quote_end = cursor
    out.append(line[cursor:])
    return _SOUND_QUOTE.sub(lambda m: m.group(1), ''.join(out))

def split_act_source(story):
    """Return (exact seconds, independent six-field H3 prompt), or None."""
    source = story.replace('\r\n', '\n').replace('\r', '\n')
    acts = list(_ACT.finditer(source))
    if not acts:
        if _ACT_LIKE.search(source):
            raise ValueError('ACT 時間格式需為 ACT 01｜00:00.000–00:10.000。')
        return None
    intro = source[:acts[0].start()]
    shared_head = _SHARED.search(intro)
    if not shared_head:
        raise ValueError('ACT 通告單前缺少【共同設定】；請保留固定角色與世界規則。')
    shared_end = _STORY_START.search(intro, shared_head.end())
    shared = intro[shared_head.end():shared_end.start() if shared_end else len(intro)].strip()
    shared = _COMPILER_META.sub('', shared).strip(' \n─-')
    if not shared:
        raise ValueError('ACT 的【共同設定】沒有內容。')
    cast = {int(number): name for number, name in _BINDING.findall(shared)}
    if not cast:
        raise ValueError('共同設定缺少 @圖片N = 角色名 綁定。')
    chapters = []
    previous = 0.0
    for i, act in enumerate(acts):
        number = int(act.group('number'))
        start, end = _clock(act.group('start')), _clock(act.group('end'))
        if number != i + 1 or abs(start - previous) > 0.01 or end <= start:
            raise ValueError('ACT 必須從 01 開始，時間連續、不重疊，並依序連號。')
        duration = end - start
        body = source[act.end():acts[i+1].start() if i+1 < len(acts) else len(source)]
        local = _field(body, 'H3 提示詞') or _field(body, 'H3提示詞')
        if not local:
            raise ValueError(f'ACT {number:02d} 缺少【H3 提示詞】。')
        beats = list(_BEAT.finditer(local))
        if not beats:
            raise ValueError(f'ACT {number:02d} 缺少「0–3秒：」這種段內鏡頭時間。')
        if abs(float(beats[0].group('start'))) > 0.01 or abs(float(beats[-1].group('end')) - duration) > 0.01:
            raise ValueError(f'ACT {number:02d} 鏡頭必須從 0 秒開始，到 {duration:g} 秒結束。')
        shots = []
        last = 0.0
        for j, beat in enumerate(beats):
            beat_start, beat_end = float(beat.group('start')), float(beat.group('end'))
            if abs(beat_start-last) > 0.01 or beat_end <= beat_start or beat_end > duration + 0.01:
                raise ValueError(f'ACT {number:02d} 的段內鏡頭時間不連續。')
            stop = beats[j+1].start() if j+1 < len(beats) else len(local)
            action = local[beat.end():stop].strip()
            if not action:
                raise ValueError(f'ACT {number:02d} 第 {j+1} 鏡沒有拍攝事件。')
            action = _tag_speech(action, cast)
            if '<d>' not in action:
                action += '\nSound for this shot: physical effects and natural ambience only. All actors remain silent with closed mouths.'
            else:
                action += '\nSound for this shot: precisely the scripted character dialogue, plus physical effects and natural ambience. No other human or animal vocalization.'
            camera = f'[Shot {j+1}]' + (f' At {_stamp(beat_start)},' if j else '')
            shots.append(camera + ' ' + action)
            last = beat_end
        entrance = _inline(body, '入鏡')
        name = _inline(body, '段落')
        setup = _field(body, '場景')
        incoming = _field(body, '承接')
        emotion = _field(body, '角色表情')
        outgoing = _field(body, '交棒')
        effects = _field(body, '音效')
        prefix = '\n'.join(filter(None, (
            'CURRENT ACT ONLY; film its timed shots once, in order.',
            'Active cast: ' + entrance if entrance else '',
            'Location: ' + setup if setup else '',
            'Incoming physical state: ' + incoming if incoming else '',
            'Acting and facial emotion: ' + emotion if emotion else '',
        )))
        shots[0] = shots[0].replace('[Shot 1] ', '[Shot 1] ' + prefix + '\n', 1)
        name = re.sub(r'[「」『』]', '', name)
        h3 = '\n\n'.join((
            'subject_definitions:\n' + shared,
            f'summary:\nFilm ACT {number:02d}' + (f' ({name})' if name else '') +
            f' in {duration:g} seconds. Do not perform later ACT events. Spoken words are restricted to explicitly tagged character dialogue spans. ' +
            'Every other description, scene direction, quoted prop text, and setting is silent instruction, never narration. ' +
            'Finish authored dialogue at least 0.65 seconds before the clip ends.',
            'retention_analysis:\n' + (f'Outgoing continuity state: {outgoing}' if outgoing else 'Preserve established appearance and scene continuity.'),
            'detailed_description:\n' + '\n\n'.join(shots),
            'overall_soundscape:\nAudio contains only synchronized, explicitly tagged character dialogue, plus authored environmental and physical sound effects. ' +
            'Start with scene ambience, not an opening vocal. Dialogue begins only at its assigned scripted shot; never synthesize spoken production notes, scene descriptions, invented words, grunts, crowd speech, chants, or ad-lib narration. ' +
            'No background music.' + ('\n' + effects if effects else ''),
            'non_diegetic_music:\nNo background music.',
        ))
        chapters.append((duration, h3))
        previous = end
    return chapters



def _act_blocks(story):
    """Read ACT boundaries only. Never turn their content into H3 speech."""
    source = story.replace('\r\n', '\n').replace('\r', '\n')
    markers = list(_ACT.finditer(source))
    if not markers:
        if _ACT_LIKE.search(source):
            raise ValueError('ACT 時間格式需為 ACT 01｜00:00.000–00:10.000。')
        return None
    blocks = []
    previous = 0.0
    for index, marker in enumerate(markers):
        number = int(marker.group('number'))
        start = _clock(marker.group('start'))
        end = _clock(marker.group('end'))
        if number != index + 1 or abs(start - previous) > 0.01 or end <= start:
            raise ValueError('ACT 必須從 01 開始、時間連續、不重疊且依序連號。')
        body = source[marker.end():markers[index + 1].start()
                      if index + 1 < len(markers) else len(source)].strip()
        if not body:
            raise ValueError(f'ACT {number:02d} 沒有內容。')
        blocks.append((end - start, body))
        previous = end
    return source[:markers[0].start()].strip(), blocks


def split_act_commissions(story):
    """9B-only route: Python owns shared settings and ACT time windows.

    Return (shared_setup, [(seconds, original local commission)]).
    The per-ACT writing is passed to the 9B H3 director, NOT directly to H3.
    Python does not infer, tag, voice, or rewrite any local dialogue.
    """
    parsed = _act_blocks(story)
    if parsed is None:
        return None
    intro, blocks = parsed
    shared_head = _SHARED.search(intro)
    if not shared_head:
        raise ValueError('9B ACT 劇本需要在所有 ACT 前提供【共同設定】。')
    shared_end = _STORY_START.search(intro, shared_head.end())
    shared = intro[shared_head.end():shared_end.start() if shared_end else len(intro)]
    shared = _COMPILER_META.sub('', shared).strip(' \n─-')
    if not shared:
        raise ValueError('【共同設定】是空的。')
    commissions = []
    for index, (seconds, body) in enumerate(blocks, 1):
        local = _field(body, 'H3 提示詞') or _field(body, 'H3提示詞')
        if not local:
            raise ValueError(f'ACT {index:02d} 需要【H3 提示詞】中的當段故事與台詞。')
        beats = list(_BEAT.finditer(local))
        if not beats or abs(float(beats[0].group('start'))) > 0.01 or abs(
                float(beats[-1].group('end')) - seconds) > 0.01:
            raise ValueError(f'ACT {index:02d} 段內鏡頭必須從 0 到 {seconds:g} 秒。')
        last = 0.0
        for beat in beats:
            start, end = float(beat.group('start')), float(beat.group('end'))
            if abs(start - last) > 0.01 or not start < end <= seconds + 0.01:
                raise ValueError(f'ACT {index:02d} 段內秒數不連續。')
            last = end
        scene = _field(body, '場景')
        opening = _field(body, '承接')
        emotion = _field(body, '角色表情')
        sound = _field(body, '音效')
        outgoing = _field(body, '交棒')
        entrance = _inline(body, '入鏡')
        title = _inline(body, '段落')
        # These are author-authored directions, not H3 output sections.
        # 9B receives exactly this ACT and the stable shared_setup separately.
        brief = '\n'.join(part for part in (
            f'ACT {index:02d}｜{seconds:g}秒；只拍這一幕，不拍其他幕。',
            '當段名稱：' + title if title else '',
            '當段入鏡：' + entrance if entrance else '',
            '當段場景：\n' + scene if scene else '',
            '當段開場狀態：\n' + opening if opening else '',
            '當段表演情緒：\n' + emotion if emotion else '',
            '當段鏡頭、動作與指定台詞（依原文順序與時間，不改台詞）：\n' + local,
            '當段環境音與音效：\n' + sound if sound else '',
            '當段交棒結果（只作連續性）：\n' + outgoing if outgoing else '',
        ) if part)
        commissions.append((seconds, brief))
    return shared, commissions


def split_kitchen_act_commissions(menu, shared_setup):
    """Keep the ACT windows and plain SHOT directions from a kitchen order."""
    parsed = _act_blocks(menu)
    if parsed is None:
        return None
    intro, blocks = parsed
    if not shared_setup and _SHARED.search(intro) and all(
            _field(body, 'H3 提示詞') or _field(body, 'H3提示詞') for _, body in blocks):
        return split_act_commissions(menu)
    if not shared_setup and (heading := _SHARED.search(intro)):
        end = _STORY_START.search(intro, heading.end())
        shared_setup = intro[heading.end():end.start() if end else len(intro)].strip()
    commissions = []
    for index, (seconds, body) in enumerate(blocks, 1):
        body = re.sub(r'(?m)^[ \t]*[━─═]{3,}[ \t]*\n?', '', body).strip()
        if index == len(blocks):
            body = re.sub(r'(?i)(?:^|\n)[ \t]*END[ \t]*\Z', '', body).rstrip()
        commissions.append((seconds, f'ACT {index:02d}｜{seconds:g}秒\n{body}'))
    return shared_setup, commissions


def split_act_native(story):
    """9B-off route: split independent, fully-authored native H3 ACT blocks.

    Nothing is prepended or extracted. A global shared block is not a
    manually completed prompt and cannot be silently replicated to all ACTs.
    """
    parsed = _act_blocks(story)
    if parsed is None:
        return None
    intro, blocks = parsed
    if intro:
        raise ValueError('關閉 9B 的純提示詞模式：ACT 前不可放共同設定或全片說明；請把完整六欄 H3 全咒各自寫在每個 ACT 內。')
    from banana_mv.direction_contract import validate_h3_sections
    clips = []
    for index, (seconds, body) in enumerate(blocks, 1):
        if not body.startswith('subject_definitions:'):
            raise ValueError(f'關閉 9B 的 ACT {index:02d} 需要使用者提供完整的六欄 H3 原生提示詞；Python 不代寫、不複製共同設定。')
        validate_h3_sections(body)
        clips.append((seconds, body))
    return clips
