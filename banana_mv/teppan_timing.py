"""蕉彌鐵板燒的時間管理：秒數由 Python 決定，9B 只負責戲。

9B 很會寫戲，但數學不可靠。以前讓 9B 自己填每段秒數，只要填出 11、12 秒，
Python 就退稿重寫；開 16K thinking 時每次重寫都很久，看起來就像無限卡住。

現在的分工：
- estimate_menu()   蕉彌先看菜單估秒數（不用 GPU，馬上有結果）。
- clip_windows()    依總秒數切出合法生成窗（每段最多 10 秒）。
- fit_segments()    9B 回幾段都收下，Python 合併／拆分到剛好符合生成窗，
                    再把秒數覆蓋成生成窗的值。9B 填的秒數完全不採用。
- native_h3_clips() 辨識使用者直接貼的 MiniMax H3 六欄全咒，跳過 9B。
"""
import math
import re

FPS = 24
MIN_CLIP = 124 / FPS          # H3 最短合法長度（約 5.17 秒）
DEFAULT_CAP = 10.0            # 5070 平衡點：一段最多 10 秒
TINY_TAIL = 1.5               # 小於這個秒數的尾巴直接捨去，不值得多開一段
SECONDS_PER_CLIP_RENDER = 90  # 6 步 480P 10 秒一段約 1 分半（出餐時間預估用）

# 中文台詞語速：每秒約 4 字，加上說完後的反應時間。
SPEECH_CHARS_PER_SECOND = 4.0
LINE_REACTION_SECONDS = 0.6
ACTION_SECONDS = 2.5          # 一個動作／事件句大約演多久

_QUOTE = re.compile(r'「([^」]*)」|『([^』]*)』|“([^”]*)”|"([^"\n]*)"')
_SENTENCE_END = re.compile(r'(?<=[。！？!?；;\n])')
_DECLARED = re.compile(
    r'(?:片長|長度|秒數|時長|全片|這道|本道|總長)\s*[：:為是約]?\s*(?:正好\s*)?'
    r'(\d+(?:\.\d+)?)\s*(秒|s\b|sec|分鐘|分|min)', re.I)
_CLIP = re.compile(
    r'(?im)^[ \t]*===\s*CLIP\s+([1-9]\d*)\s*'
    r'\(\s*(\d+(?:\.\d+)?)\s*s(?:ec(?:onds?)?)?\s*\)\s*===\s*$')
_FENCE = re.compile(r'```(?:text|h3|plaintext)?[ \t]*\n([\s\S]*?)\n```[ \t]*', re.I)


_CLOCK = r'(?:\d{1,2}:)?\d{1,2}:[0-5]\d(?:\.\d+)?'
_TIMELINE_RANGE = re.compile(
    rf'(?m)^[ \t]*(?:\#{{1,6}}[ \t]+)?(?:'
    rf'(?:第[一二三四五六七八九十百零〇\d]+[幕場段]|(?:MINIMAX H3 專用提示詞[｜|][ \t]*)?場景[ \t]*\d+|(?:ACT|SCENE|CLIP|SHOT)[ \t]+\d+)[^：:\n（(]*[（(]?[ \t]*'
    rf'|[（(]?)({_CLOCK})[ \t]*[–—~～-][ \t]*({_CLOCK})'
    rf'[ \t]*[）)]?(?=[ \t]*(?:$|[｜|：:]))', re.I)


def _timeline_seconds(menu):
    def seconds(clock):
        return sum(float(part) * 60**i for i, part in enumerate(reversed(clock.split(':'))))

    ranges = sorted((seconds(start), seconds(end)) for start, end in _TIMELINE_RANGE.findall(menu))
    end_time = 0.0
    for start, end in ranges:
        if end <= start:
            continue
        if start > end_time + 0.05:
            return None
        end_time = max(end_time, end)
    return end_time or None


def _frame(seconds):
    return round(seconds * FPS) / FPS


def clip_windows(total, cap=DEFAULT_CAP, minimum=MIN_CLIP):
    """把總秒數切成合法生成窗。每段 ≤ cap 且 ≥ minimum。

    例：10 → [10]；25 → [10, 10, 5.x 不夠 → 平分] → [10, 7.5, 7.5]；
    21 → [10, 10]（1 秒尾巴捨去）。
    """
    if not isinstance(total, (int, float)) or isinstance(total, bool) or not math.isfinite(total):
        raise ValueError('秒數需為有限數字。')
    cap = float(cap)
    total = max(float(total), minimum)
    count = max(1, math.ceil(total / cap - 1e-9))
    if count == 1:
        return [_frame(min(total, cap))]
    tail = total - (count - 1) * cap
    if tail >= minimum - 1e-9:
        windows = [cap] * (count - 1) + [tail]
    elif tail < TINY_TAIL:
        windows = [cap] * (count - 1)
    else:
        half = (cap + tail) / 2
        windows = [cap] * (count - 2) + [half, half]
    return [_frame(w) for w in windows]


def _strip_fence(text):
    source = text.strip()
    fence = _FENCE.fullmatch(source)
    return fence[1].strip() if fence else source


def native_h3_clips(menu, dish_seconds, cap=DEFAULT_CAP):
    """使用者自己寫好的 H3 六欄全咒 → [(秒數, 全咒)]；不是全咒就回傳 None。

    - 一整段以 subject_definitions: 開頭 → 單段，秒數取這道菜的秒數（最多 cap）。
    - === CLIP 1 (10s) === 分段，且每段都是六欄全咒 → 照使用者標的秒數。
    粗 CUE（一般文字）一律回傳 None，交給 9B 展開。
    """
    if not isinstance(menu, str):
        return None
    source = _strip_fence(menu)
    markers = list(_CLIP.finditer(source))
    if markers:
        if source[:markers[0].start()].strip():
            return None
        clips = []
        for i, marker in enumerate(markers):
            end = markers[i + 1].start() if i + 1 < len(markers) else len(source)
            body = source[marker.end():end].strip()
            if not body.startswith('subject_definitions:'):
                return None
            clips.append((float(marker[2]), body))
        for i, (seconds, _) in enumerate(clips, 1):
            if not MIN_CLIP - 1e-6 <= seconds <= cap + 1e-6:
                raise ValueError(f'H3 全咒第 {i} 段標了 {seconds:g} 秒；每段需介於 '
                                 f'{MIN_CLIP:.2f}–{cap:g} 秒。')
        return clips
    if source.startswith('subject_definitions:'):
        seconds = dish_seconds if isinstance(dish_seconds, (int, float)) else cap
        return [(_frame(min(max(float(seconds), MIN_CLIP), cap)), source)]
    return None


def estimate_menu(menu, cap=DEFAULT_CAP):
    """蕉彌估價：看菜單估秒數、段數、出餐時間。不呼叫 9B，不用 GPU。"""
    if not isinstance(menu, str) or not menu.strip():
        raise ValueError('請先寫菜單。')
    native = native_h3_clips(menu, None, cap)
    if native:
        seconds = sum(s for s, _ in native)
        windows = [s for s, _ in native]
        source = 'native_h3'
    else:
        declared = _DECLARED.search(menu)
        if declared:
            value = float(declared[1])
            seconds = value * 60 if declared[2].lower() in ('分鐘', '分', 'min') else value
            source = 'declared'
        elif (timeline := _timeline_seconds(menu)) is not None:
            seconds = timeline
            source = 'timecode'
        else:
            lines = [next(filter(None, m.groups()), '') for m in _QUOTE.finditer(menu)]
            speech = sum(len(re.sub(r'\s', '', line)) for line in lines)
            remainder = _QUOTE.sub('', menu)
            actions = [s for s in (p.strip() for p in _SENTENCE_END.split(remainder))
                       if len(re.sub(r'[\s，,。！？!?；;：:]', '', s)) >= 4]
            seconds = (speech / SPEECH_CHARS_PER_SECOND + LINE_REACTION_SECONDS * len(lines)
                       + ACTION_SECONDS * len(actions))
            source = 'estimate'
        seconds = min(300.0, max(6.0, seconds))
        windows = clip_windows(seconds, cap)
        seconds = sum(windows)
    return {'seconds': round(seconds, 3), 'windows': windows, 'clips': len(windows),
            'render_seconds': len(windows) * SECONDS_PER_CLIP_RENDER,
            'source': source, 'native_h3': source == 'native_h3'}


def _split_brief(brief):
    """在最接近中間的句尾把一段委託切成兩段；切不了回傳 None。"""
    pieces = [p for p in _SENTENCE_END.split(brief) if p]
    if len(pieces) < 2:
        return None
    total = len(brief)
    best, best_gap, running = None, None, 0
    for i in range(1, len(pieces)):
        running += len(pieces[i - 1])
        gap = abs(running - total / 2)
        if best_gap is None or gap < best_gap:
            best, best_gap = i, gap
    first = ''.join(pieces[:best]).strip()
    second = ''.join(pieces[best:]).strip()
    if len(first) < 20 or len(second) < 20:
        return None
    return first, '（緊接上一段，不重演已發生的事）' + second


def fit_segments(rows, windows, cap=DEFAULT_CAP):
    """9B 回幾段都收下，整理成剛好 len(windows) 段，秒數改成 Python 的值。

    - 段數太多：把最短的相鄰兩段合併。
    - 段數太少：把最長的一段在句尾拆成兩段。
    - 實在拆不開：減少生成窗（合併最後兩窗、最多 cap 秒），寧可短一點也不卡住。
    回傳 (segments, windows)。
    """
    if not isinstance(rows, list) or not rows:
        raise ValueError('9B 沒有回傳任何段落。')
    segments = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('brief'), str):
            raise ValueError('每個段落需有文字委託 brief。')
        mode = row.get('mode') if row.get('mode') in ('story', 'action') else 'story'
        segments.append({'mode': mode, 'brief': row['brief'].strip()})
    windows = list(windows)
    while len(segments) > len(windows):
        pair = min(range(len(segments) - 1),
                   key=lambda i: len(segments[i]['brief']) + len(segments[i + 1]['brief']))
        a, b = segments[pair], segments[pair + 1]
        mode = 'action' if 'action' in (a['mode'], b['mode']) else 'story'
        segments[pair:pair + 2] = [{'mode': mode, 'brief': a['brief'] + '\n' + b['brief']}]
    while len(segments) < len(windows):
        order = sorted(range(len(segments)), key=lambda i: -len(segments[i]['brief']))
        for index in order:
            halves = _split_brief(segments[index]['brief'])
            if halves:
                mode = segments[index]['mode']
                segments[index:index + 1] = [{'mode': mode, 'brief': h} for h in halves]
                break
        else:
            merged = min(cap, windows[-2] + windows[-1])
            windows[-2:] = [_frame(merged)]
    for segment, seconds in zip(segments, windows):
        segment['seconds'] = seconds
    return segments, windows
