"""蕉彌鐵板燒：拍到一半換角色。

使用者在輸入框打指令，Python 只照字面改「共同設定框」裡的文字，不猜：

  取代@圖片3        換第 3 張圖；下面寫新的綁定行「@圖片3＝小狐＝S9」和聲音描述
  新增              接一張新圖在最後；下面寫「@圖片K＝名字＝SN」（K＝目前張數＋1）和聲音描述
  移除@圖片5        拿掉第 5 張圖、它的綁定行和那個 S 代號的描述，後面的圖號往前補

「S 代號的描述」＝行首是那個 S 代號的那一行，一直到下一個行首 S 代號、■ 或【 標題之前。
已經拍好的段保留當時的圖與設定（重拍舊段不會換成新角色）；還沒拍的段從下一段開始用新設定。
"""
import re

_PICTURE = re.compile(r'(?:@(?:圖片|图片|image)[ \t]*(\d+)|<Picture[ \t]+(\d+)>)', re.I)
_BINDING = re.compile(
    r'^[ \t]*(?:[-*•][ \t]*)?(?:@(?:圖片|图片|image)[ \t]*(\d+)|<Picture[ \t]+(\d+)>)[ \t]*[=＝][ \t]*'
    r'([^\n=＝]*?)[ \t]*[=＝][ \t]*(S\d+)(?!\d)', re.I)
_ROLE_LINE = re.compile(r'^[ \t]*(?:[-*•][ \t]*)?(S\d+)(?!\d)', re.I)
_HEADING = re.compile(r'^[ \t]*[■【]')
_COMMAND = re.compile(
    r'\A[ \t]*(?:(?P<verb>取代|替換|換掉|移除|刪除)[ \t]*[@＠](?:圖片|图片|image)?[ \t]*(?P<number>\d+)'
    r'|(?P<add>新增))[ \t]*(?:\n|\Z)', re.I)


def parse(text):
    """回傳 (動作, 圖號或 None, 下面的內容)；不是換角指令就回傳 None。"""
    match = _COMMAND.match(text or '')
    if not match:
        return None
    rest = text[match.end():].strip('\n')
    if match['add']:
        return 'add', None, rest
    action = 'remove' if match['verb'] in ('移除', '刪除') else 'replace'
    return action, int(match['number']), rest


def to_display(shared):
    """內部 <Picture N> 換回使用者看得懂的 @圖片N（同一個編號）。"""
    return re.sub(r'<Picture[ \t]+(\d+)>', r'@圖片\1', shared or '')


def to_internal(display):
    return re.sub(r'@(?:圖片|图片|image)[ \t]*(\d+)', r'<Picture \1>', display or '', flags=re.I)


def _number(match):
    return int(match[1] or match[2])


def binding_role(text, number):
    for line in (text or '').splitlines():
        match = _BINDING.match(line)
        if match and _number(match) == number:
            return match[4].upper()
    return None


_LINE_NUMBER = re.compile(r'(?:@(?:圖片|图片|image)[ \t]*(\d+)|<Picture[ \t]+(\d+)>)', re.I)


def _binding_index(lines, number):
    """第 number 張圖的綁定行（角色或場景都算）。"""
    for index, line in enumerate(lines):
        if _PICTURE_LINE.match(line) and _number(_LINE_NUMBER.search(line)) == number:
            return index
    return None


_PICTURE_LINE = re.compile(r'^[ \t]*(?:[-*•][ \t]*)?(?:@(?:圖片|图片|image)[ \t]*\d+|<Picture[ \t]+\d+>)[ \t]*[=＝]', re.I)


def _last_binding(lines):
    """最後一行「@圖片N＝…」（含場景圖）：新綁定接在它後面。"""
    found = None
    for index, line in enumerate(lines):
        if _PICTURE_LINE.match(line):
            found = index
    return found


def _after_roles(lines):
    """最後一個 S 代號段落結束的位置（下一個標題前、去掉尾端空行）；沒有就回傳 None。"""
    last = None
    for index, line in enumerate(lines):
        if _ROLE_LINE.match(line) and not _BINDING.match(line):
            last = index
    if last is None:
        return None
    end = next((i for i in range(last + 1, len(lines)) if _HEADING.match(lines[i])), len(lines))
    while end > last + 1 and not lines[end - 1].strip():
        end -= 1
    return end


def remove_role(lines, role):
    """刪掉每個行首是 role 的段落；回傳 (新的行, 第一段原本的位置, 刪掉的行)。"""
    role = role.upper()
    kept, removed, first, skipping = [], [], None, False
    for line in lines:
        head = _ROLE_LINE.match(line)
        if head and not _BINDING.match(line):
            skipping = head[1].upper() == role
            if skipping and first is None:
                first = len(kept)
        elif _HEADING.match(line) or _BINDING.match(line):
            skipping = False
        if skipping:
            removed.append(line)
        else:
            kept.append(line)
    # 段落之間原本的空行：刪掉的段落後面若連著兩個空行，收成一個。
    if first is not None:
        while first < len(kept) - 1 and not kept[first].strip() and first and not kept[first - 1].strip():
            del kept[first]
    while removed and not removed[-1].strip():
        removed.pop()
    return kept, first, removed


def renumber(text, removed):
    """拿掉第 removed 張圖：後面的圖號往前補一號（@圖片N 與 <Picture N> 都改）。"""
    def shift(match):
        number = _number(match)
        if number <= removed:
            return match[0]
        return f'@圖片{number - 1}' if match[1] else f'<Picture {number - 1}>'
    return _PICTURE.sub(shift, text or '')


def _insert_block(lines, position, block):
    if not block:
        return lines
    if position is None:
        position = _after_roles(lines)
    if position is None:
        tail = lines[:]
        while tail and not tail[-1].strip():
            tail.pop()
        return tail + ([''] if tail else []) + block
    before = [''] if position and lines[position - 1].strip() else []
    after = [''] if position < len(lines) and lines[position].strip() else []
    return lines[:position] + before + block + after + lines[position:]


def _split_new(rest, number):
    """指令下面的內容：一行綁定（圖號必須是 number）＋其他行（聲音、外觀描述）。"""
    lines = rest.splitlines()
    bindings = [index for index, line in enumerate(lines) if _PICTURE_LINE.match(line)]
    if len(bindings) != 1:
        raise ValueError(f'指令下面要寫一行綁定，例如「@圖片{number}＝小狐＝S9」。')
    index = bindings[0]
    line = lines[index]
    if _number(_LINE_NUMBER.search(line)) != number:
        raise ValueError(f'這張圖會是 @圖片{number}，綁定行請寫「@圖片{number}＝…」。')
    match = _BINDING.match(line)
    if match:
        role, name = match[4].upper(), match[3].strip()
        binding = f'@圖片{number}＝{name}＝{role}'
    else:   # 場景、道具圖：沒有 S 代號
        role, name = None, re.split(r'[=＝]', line, 1)[1].strip()
        binding = f'@圖片{number}＝{name}'
    if not name:
        raise ValueError(f'綁定行要寫名稱，例如「@圖片{number}＝小狐＝S9」。')
    block = [text for i, text in enumerate(lines) if i != index]
    while block and not block[0].strip():
        block.pop(0)
    while block and not block[-1].strip():
        block.pop()
    if block and role and not _ROLE_LINE.match(block[0]):
        # 聲音描述沒寫 S 代號開頭：補一行，之後才刪得乾淨。
        block.insert(0, f'{role} {name}：')
    return binding, role, name, block


def apply(display, action, number, rest, count, limit):
    """改共同設定文字。回傳 (新文字, 新圖片張數, 蕉彌的回覆)。"""
    lines = (display or '').splitlines()
    if action == 'add':
        number = count + 1
        if number > limit:
            raise ValueError(f'參考圖已經 {count} 張，最多 {limit} 張；先「移除@圖片N」騰出位置。')
        binding, role, name, block = _split_new(rest, number)
        anchor = _last_binding(lines)
        lines = lines[:anchor + 1] + [binding] + lines[anchor + 1:] if anchor is not None else [binding, ''] + lines
        lines = _insert_block(lines, None, block)
        reply = f'新增 @圖片{number}：{name}' + (f'（{role}）' if role else '') + ('，聲音與描述也加進共同設定。' if block else '。')
        return '\n'.join(lines).strip('\n'), count + 1, reply
    if not 1 <= number <= count:
        raise ValueError(f'找不到 @圖片{number}，目前只有 {count} 張參考圖。')
    old_role = binding_role(display, number)
    position = _binding_index(lines, number)
    if action == 'remove':
        if position is not None:
            del lines[position]
        removed = []
        if old_role:
            lines, _, removed = remove_role(lines, old_role)
        text = renumber('\n'.join(lines), number).strip('\n')
        parts = [f'移除 @圖片{number}' + (f'（{old_role}）' if old_role else '')]
        if removed:
            parts.append(f'刪掉 {old_role} 的描述 {len(removed)} 行')
        if number < count:
            parts.append(f'@圖片{number + 1} 之後的圖號往前補一號')
        return text, count - 1, '，'.join(parts) + '。'
    binding, role, name, block = _split_new(rest, number)
    if position is not None:
        lines[position] = binding
    else:
        anchor = _last_binding(lines)
        lines = lines[:anchor + 1] + [binding] + lines[anchor + 1:] if anchor is not None else [binding, ''] + lines
    removed, at = [], None
    if block and role and role != old_role:
        lines, at, removed = remove_role(lines, role)     # 新代號若已有舊描述，也一併換掉
    if old_role and (block or old_role != role):
        lines, first, more = remove_role(lines, old_role)
        removed += more
        at = first if first is not None else at
    lines = _insert_block(lines, at, block)
    reply = f'@圖片{number} 換成 {name}' + (f'（{role}）' if role else '')
    if removed:
        reply += f'，已刪掉舊的 {old_role or role} 描述'
    if block:
        reply += '，加上新的聲音與描述'
    return '\n'.join(lines).strip('\n'), count, reply + '。'
