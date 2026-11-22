"""Small deterministic reference and ending-scope checks."""
from collections import Counter
import re
import unicodedata

_TERMINAL = re.compile(r'最後(?:畫面|一鏡|鏡頭)|最終(?:畫面|鏡頭)|結尾(?:畫面|鏡頭)|\b(?:final image|final shot|last shot|terminal shot|closing image)\b', re.I)


def scoped_constraints(constraints, final):
    """Legacy string constraints are split at sentences, preserving role clauses."""
    clauses = [part.strip() for text in constraints
               for part in re.split(r'(?<=[.!?。！？;；])\s*', text) if part.strip()]
    return [text for text in clauses if final or not _TERMINAL.search(text)]


def validate_subject_bindings(text, appearance):
    """Check explicit actor declarations only; never infer roles from prose."""
    definitions=text.split('summary:',1)[0] if 'subject_definitions:' in text else ''
    for sid,picture in re.findall(r'^\s*<Subject (\d+)>[^\n]*?<Picture (\d+)>',definitions,re.M):
        expected=appearance['characters'].get('S'+sid,{}).get('connected_reference')
        if expected and expected!=f'<Picture {picture}>':
            raise ValueError(f'<Subject {sid}> 必須綁定 {expected}，不可改為 <Picture {picture}>。')


H3_SECTIONS=('subject_definitions','summary','retention_analysis','detailed_description',
             'overall_soundscape','non_diegetic_music')


def last_complete_h3(text):
    """9B 有時在一份回覆裡把六欄全咒寫兩三遍（寫完又「修正版」重寫）。
    只保留最後一份依序完整的六欄；只有一份或找不到完整一份時原樣回傳。"""
    headers=list(re.finditer(r'^[ \t]*('+'|'.join(H3_SECTIONS)+r')[ \t]*:',text,re.M))
    if len(headers)<=len(H3_SECTIONS):
        return text
    size=len(H3_SECTIONS)
    for start in range(len(headers)-size,-1,-1):
        if tuple(match[1] for match in headers[start:start+size])==H3_SECTIONS:
            end=headers[start+size].start() if start+size<len(headers) else len(text)
            return text[headers[start].start():end].strip()
    return text


def validate_h3_sections(text):
    """Check the native six-field contract, without interpreting the story."""
    headers=list(re.finditer(r'^\s*('+'|'.join(H3_SECTIONS)+r')\s*:',text,re.M))
    if tuple(match[1] for match in headers)!=H3_SECTIONS:
        raise ValueError('Ref2VA 需依序包含六個區塊：'+', '.join(H3_SECTIONS))
    for i,match in enumerate(headers):
        end=headers[i+1].start() if i+1<len(headers) else len(text)
        if not text[match.end():end].strip():
            raise ValueError('Ref2VA 區塊不可空白：'+match[1])


_CAST_LINE = re.compile(r'^\s*<Picture (\d+)>\s*[=＝]\s*([^，,：:\s。；;]+)', re.M)
_QUOTED_LINE = re.compile(r'「([^」\n]+)」|『([^』\n]+)』')
_VOICE_CUE = re.compile(
    r'(?:說|問|喊|吼|答|提醒|回應|低語|嘀咕|抱怨|忍笑|鎮定|旁白|開口)[^：:\n，,。！？；;]{0,8}[：:]\s*$'
)
_SPEAKER_CUE = re.compile(r'<Subject (\d+)>\s*\(S\d+\)\s*[:：,，]?\s*$', re.I)
_SPEECH_VERB = re.compile(
    r'\b(?:says?|asks?|replies|reply|answers?|whispers?|calls?|shouts?|'
    r'announces?|murmurs?|mutters?|adds?|responds?)\b', re.I
)
_SUBJECT = re.compile(r'<Subject (\d+)>', re.I)
_SENTENCE_BREAK = re.compile(r'<\/d>|\[Shot \d+\]|[。！？!?]|\.(?=\s|$)|\n', re.I)
_VOICE_LINE = re.compile(r'<d>\s*(?:\[[^\]\n]+\]\s*)?(.*?)\s*</d>', re.S)


def authored_dialogue(brief, shared):
    """Lock only quoted speech with a uniquely named reference actor."""
    cast = [(name, int(picture)) for picture, name in _CAST_LINE.findall(shared)]
    if not cast:
        return []
    names = '|'.join(map(re.escape, sorted({name for name, _ in cast}, key=len, reverse=True)))
    addressed = re.compile(
        rf'(?P<speaker>{names})\s*(?:轉身\s*)?(?:對著?|朝著?|向|看向|望向)\s*(?:{names})\s*'
        + _VOICE_CUE.pattern
    )
    locks, after_quote = [], 0
    for quote in _QUOTED_LINE.finditer(brief):
        lead = re.split(r'[\n。！？；;]', brief[after_quote:quote.start()])[-1]
        after_quote = quote.end()
        if not _VOICE_CUE.search(lead):
            continue
        speakers = {(name, picture) for name, picture in cast
                    if name in lead or f'<Picture {picture}>' in lead}
        if len(speakers) > 1 and (exchange := addressed.search(lead)):
            speakers = {(name, picture) for name, picture in speakers if name == exchange['speaker']}
        if len(speakers) == 1:
            name, picture = speakers.pop()
            locks.append({'speaker': name, 'reference': f'<Picture {picture}>',
                          'line': quote[1] or quote[2]})
    return locks


def _line_key(line):
    return ''.join(char for char in unicodedata.normalize('NFKC', line)
                   if not char.isspace() and not unicodedata.category(char).startswith('P'))


def _dialogue_subject(context):
    # Prefer explicit speech attribution over a nearby tag on the addressee.
    sentence = _SENTENCE_BREAK.split(context.rstrip())[-1]
    verbs = list(_SPEECH_VERB.finditer(sentence))
    if verbs:
        actors = set(_SUBJECT.findall(sentence[:verbs[-1].start()]))
        if len(actors) == 1:
            return next(iter(actors))
        return None
    cue = _SPEAKER_CUE.search(sentence)
    return cue[1] if cue else None


def validate_authored_dialogue(prompt, locks):
    if not locks:
        return
    definitions = prompt.split('summary:', 1)[0]
    references = {}
    for row in definitions.splitlines():
        subject = re.match(r'\s*<Subject (\d+)>', row)
        picture = re.match(r'\s*<Picture (\d+)>\s+(?:is|=)\s+<Subject (\d+)>', row, re.I)
        if subject:
            found = set(re.findall(r'<Picture \d+>', row))
            if len(found) == 1:
                references.setdefault(subject[1], set()).update(found)
        elif picture:
            references.setdefault(picture[2], set()).add(f'<Picture {picture[1]}>')
    shots = prompt.partition('detailed_description:')[2].split('overall_soundscape:', 1)[0]
    actual = Counter()
    expected_lines = {_line_key(lock['line']) for lock in locks}
    for line in _VOICE_LINE.finditer(shots):
        key = _line_key(line[1])
        if key not in expected_lines:
            continue
        subject = _dialogue_subject(shots[:line.start()])
        found = references.get(subject, set())
        actual[key, next(iter(found)) if len(found) == 1 else None] += 1
    for lock in locks:
        key = _line_key(lock['line'])
        expected = Counter(other['reference'] for other in locks if _line_key(other['line']) == key)
        delivered = Counter({ref: count for (line, ref), count in actual.items() if line == key})
        if delivered != expected:
            raise ValueError(f'指定台詞「{lock["line"]}」說話者或出現次數不符。'
                             f'依 authored_dialogue 綁定 {lock["speaker"]}（{lock["reference"]}），'
                             '使用 <Subject N> (Sx) <d>[Chinese] 台詞</d>。')

