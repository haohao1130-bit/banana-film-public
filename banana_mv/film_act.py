"""Read authored ACT timelines as isolated native MiniMax H3 film commissions.

This adapter is deliberately opt-in: an ACT time ruler must be present. Existing
CLIP, SEGMENT, SHOT and freeform film paths are unaffected.
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


def _clock(value):
    minutes, seconds = value.split(':', 1)
    return int(minutes) * 60 + float(seconds)


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
    """Mark only explicit speech, not quoted prop names or written placards."""
    out = []
    cursor = 0
    prior_quote_end = 0
    for quote in _QUOTE.finditer(line):
        out.append(line[cursor:quote.start()])
        before = line[prior_quote_end:quote.start()]
        speaker_phrase = before.rsplit('。', 1)[-1].rsplit('；', 1)[-1]
        if _SPEECH.search(speaker_phrase):
            possible = []
            for number, name in cast.items():
                for token in (name, f'@圖片{number}', f'<Picture {number}>'):
                    position = speaker_phrase.rfind(token)
                    if position >= 0:
                        possible.append((position, number))
            if '赤兔馬' in speaker_phrase:
                possible.append((speaker_phrase.rfind('赤兔馬'), 6))
            if possible:
                speaker = max(possible)[1]
                out.append(f'(S{speaker}) <d>[Chinese] {quote.group(1)}</d>')
            else:
                out.append(quote.group(0))
        else:
            out.append(quote.group(0))
        cursor = quote.end()
        prior_quote_end = cursor
    out.append(line[cursor:])
    return ''.join(out)


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
    shared = shared.strip(' \n─-')
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
        h3 = '\n\n'.join((
            'subject_definitions:\n' + shared,
            f'summary:\nFilm ACT {number:02d}' + (f' ({name})' if name else '') + f' in {duration:g} seconds. Do not perform later ACT events. Finish spoken lines at least 0.65 seconds before the clip ends; use the rest for silent acting and ambience.',
            'retention_analysis:\n' + (f'Outgoing continuity state: {outgoing}' if outgoing else 'Preserve established appearance and scene continuity.'),
            'detailed_description:\n' + '\n\n'.join(shots),
            'overall_soundscape:\nNo music; use only spoken dialogue, voiceover, environmental sound and sound effects.' + ('\n' + effects if effects else ''),
            'non_diegetic_music:\nNo background music.',
        ))
        chapters.append((duration, h3))
        previous = end
    return chapters
