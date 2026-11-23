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


_CAST_LINE = re.compile(r'^\s*<Picture (\d+)>\s*[=＝]\s*([^，,：:\s。；;=＝]+)', re.M)
# 「<Picture 2>＝小貓＝S2」：名字之後的 S 代號也是這個角色（菜單常寫「S5對S2說」）。
_CAST_ROLE_LINE = re.compile(r'^\s*<Picture (\d+)>\s*[=＝]\s*[^，,：:\s。；;=＝]+\s*[=＝]\s*(S[1-8])(?![0-9])', re.M | re.I)
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
    named = {int(picture): name for picture, name in _CAST_LINE.findall(shared)}
    if not named:
        return []
    # 名字與 S 代號都是同一個角色的稱呼；鎖定時一律回報名字。
    cast = [(name, picture) for picture, name in named.items()]
    cast += [(role.upper(), int(picture)) for picture, role in _CAST_ROLE_LINE.findall(shared)]
    names = '|'.join(map(re.escape, sorted({name for name, _ in cast}, key=len, reverse=True)))
    def mentioned(alias, lead):
        if re.fullmatch(r'S[1-8]', alias):
            return re.search(rf'(?<![A-Za-z0-9]){alias}(?![0-9])', lead, re.I) is not None
        return alias in lead
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
        speakers = {picture for alias, picture in cast
                    if mentioned(alias, lead) or f'<Picture {picture}>' in lead}
        if len(speakers) > 1 and (exchange := addressed.search(lead)):
            speaker = exchange['speaker'].upper()
            speakers = {picture for alias, picture in cast if alias.upper() == speaker}
        if len(speakers) == 1:
            picture = speakers.pop()
            roles = [alias for alias, number in cast if number == picture and re.fullmatch(r'S[1-8]', alias)]
            locks.append({'speaker': named[picture], 'reference': f'<Picture {picture}>',
                          **({'role': roles[0]} if roles else {}),
                          'line': quote[1] or quote[2]})
    return locks


def _definition_rows(definitions):
    """subject_definitions 每行對應的 Subject：「<Subject 1> is … <Picture 1>」與
    「<Picture 1> is the appearance reference for <Subject 1>」兩種寫法都認。"""
    rows = {}
    for row in definitions.splitlines():
        found = re.search(r'<Subject (\d+)>', row)
        if found and re.match(r'\s*<(?:Subject|Picture) \d+>', row):
            rows[found[1]] = rows.get(found[1], '') + ' ' + row
    return rows


_TAGGED = re.compile(r'<Subject (\d+)>\s*\((S\d+)\)')


def fix_speaker_tags(prompt, locks):
    """H3 用台詞前最近的「<Subject N> (Sx)」決定誰的聲音講這句。9B 常漏標或標到聽的人
    （實測 cf9f52c7f21f 第 18 段：小浣喊「小貓！你最好了！」前最近的標籤是小貓）。
    指定台詞的最近標籤不是該講的人時，Python 在 <d> 前補上正確的說話者；找不到該角色就不動。
    回傳 (修正後的全咒, 修正了哪些台詞)。"""
    if not locks or 'detailed_description:' not in prompt:
        return prompt, []
    prompt = re.sub(r'(\(S\d+\))(?:\s*\1)+', r'\1', prompt)       # 「(S6) (S6)」→「(S6)」
    head, _, rest = prompt.partition('detailed_description:')
    shots, marker, tail = rest.partition('overall_soundscape:')
    definitions = head.split('summary:', 1)[0]
    rows = _definition_rows(definitions)

    def speaker_subject(lock):
        def own(row):
            if lock['reference'] in row:
                return True
            if lock['speaker'] in row:
                return True
            role = lock.get('role')
            return bool(role and re.search(rf'(?<![A-Za-z0-9]){role}(?![0-9])', row))
        found = [n for n, row in rows.items() if own(row)]
        named = [n for n in found if lock['speaker'] in rows[n] or lock['reference'] in rows[n]]
        return (named or found or [None])[0]

    wanted = {_line_key(lock['line']): lock for lock in locks}
    fixed, pieces, cursor = [], [], 0
    for line in _VOICE_LINE.finditer(shots):
        lock = wanted.get(_line_key(line[1]))
        if not lock:
            continue
        shot_start = max(shots.rfind('[Shot', 0, line.start()), 0)
        tags = _TAGGED.findall(shots[shot_start:line.start()])
        subject = speaker_subject(lock)
        if subject is None or (tags and tags[-1][0] == subject):
            continue
        used = {tag for _, tag in _TAGGED.findall(shots)}
        own_tag = next((tag for number, tag in _TAGGED.findall(shots) if number == subject), None)
        if own_tag is None:
            own_tag = next(f'S{k}' for k in range(1, 9) if f'S{k}' not in used)
        pieces.append(shots[cursor:line.start()])
        pieces.append(f'<Subject {subject}> ({own_tag}) says, ')
        cursor = line.start()
        fixed.append(lock['line'])
    if not fixed:
        return head + 'detailed_description:' + shots + marker + tail, []
    pieces.append(shots[cursor:])
    return head + 'detailed_description:' + ''.join(pieces) + marker + tail, fixed


def speaker_missing(prompt, locks):
    """指定台詞的說話者在 subject_definitions 裡找不到（9B 漏定義該角色），Python 無從補標。"""
    definitions = prompt.split('summary:', 1)[0]
    rows = list(_definition_rows(definitions).values())
    missing = []
    for lock in locks:
        role = lock.get('role')
        if not any(lock['reference'] in row or lock['speaker'] in row or
                   (role and re.search(rf'(?<![A-Za-z0-9]){role}(?![0-9])', row)) for row in rows):
            missing.append(lock)
    return missing


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

