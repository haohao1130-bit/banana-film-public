"""Wardrobe state transitions reused from the MV 5070 Python slot planner."""
import re

WARDROBE_KINDS = (
    ('Torso', re.compile(r'馬甲|胸衣|抹胸|上衣|襯衫|背心|皮衣|外套|夾克|制服|T恤|胸罩|內衣', re.I)),
    ('Bottom', re.compile(r'內褲|短褲|長褲|裙|泳褲|褲子|褲', re.I)),
    ('Feet', re.compile(r'高跟|舞鞋|鞋|靴|襪', re.I)),
)
SCOPE_NOTE = re.compile(r'^(?:本段|此段|這段|本章|此章)(?:只|僅|完成|保留|維持|建立)(?=.|$)')
REMOVAL = re.compile(r'卸除|脫下|脫掉|脫去|摘下|取下|移除|拿掉|褪下')
UNFASTEN = re.compile(r'解開|解扣|鬆開')
DRESS = re.compile(r'穿上|重新穿上|穿回|戴上|重新戴上|換上')


def _opening_actor_state(fixed, chapters):
    """Use only explicitly declared opening wardrobe, never future synopsis."""
    state = {}
    taking = False
    for raw in fixed.splitlines():
        line = raw.strip().lstrip('-* ').strip()
        opener = re.match(r'^(?:開場穿著|初始穿著|初始服裝|開場服裝)\s*[:：]\s*(.*)$', line)
        if opener:
            taking = True
            line = opener.group(1).strip()
        elif taking and (not line or line.endswith(('：', ':'))):
            taking = False
        elif taking and re.match(r'^(?:服裝隨|已卸除|不重新|人物|整體|故事|演唱)', line):
            taking = False
        if not taking or not line:
            continue
        for kind, pattern in WARDROBE_KINDS:
            if pattern.search(line):
                state[kind] = {'label': line, 'status': 'worn'}
    if not state and chapters and chapters[0]['actions']:
        first = chapters[0]['actions'][0]
        if re.search(r'穿著|身穿|穿上|佩戴', first):
            for kind, pattern in WARDROBE_KINDS:
                match = pattern.search(first)
                if match:
                    state[kind] = {'label': match.group(), 'status': 'worn'}
    return state


def _advance_actor_state(state, action):
    """Advance from explicit local events; never infer changes from future plot."""
    if SCOPE_NOTE.match(action):
        return
    if re.search(r'上身裸露|上身赤裸|裸露上身|赤裸上身', action) and 'Torso' in state:
        state['Torso']['status'] = 'removed'
    if '全裸' in action or '一絲不掛' in action:
        for kind in ('Torso', 'Bottom'):
            if kind in state:
                state[kind]['status'] = 'removed'
    if re.search(r'赤腳|赤足|光腳', action) and 'Feet' in state:
        state['Feet']['status'] = 'removed'
    for kind, pattern in WARDROBE_KINDS:
        if kind not in state or not pattern.search(action):
            continue
        if REMOVAL.search(action) or (UNFASTEN.search(action) and re.search(r'完成.*(?:服裝變化|卸除|脫除)', action)):
            state[kind]['status'] = 'removed'
        elif UNFASTEN.search(action):
            state[kind]['status'] = 'unfastened'
        elif DRESS.search(action):
            state[kind]['status'] = 'worn'


def _actor_state_lines(state):
    lines = []
    for kind in ('Torso', 'Bottom', 'Feet'):
        if kind not in state:
            continue
        item = state[kind]
        if item['status'] == 'removed':
            label = 'Barefoot' if kind == 'Feet' else 'Bare'
            lines.append(f'- {kind}: {label}; {item["label"]} already removed, stays off.')
        elif item['status'] == 'unfastened':
            lines.append(f'- {kind}: {item["label"]} unfastened (transitional, not reset).')
        else:
            lines.append(f'- {kind}: {item["label"]} worn.')
    return '\n'.join(lines)


# Ported without a new state machine from banana-mv-public's proven Python Slot
# experiment (banana_mv/python_slots.py + banana_mv/shoot_plan.py).
def _current_appearance_anchor(state):
    """A factual, non-filmable starting condition beside local filming actions.

    The marker is separate from new plot actions: no removal or redressing is
    staged by this line. The Python ledger remains the authority for each
    explicitly known property; unspecified properties still use the references.
    """
    names = {'Torso': '上身', 'Bottom': '下身', 'Feet': '雙腳'}
    facts = []
    for kind in ('Torso', 'Bottom', 'Feet'):
        item = state.get(kind)
        if item is None:
            continue
        label, status = item['label'], item['status']
        if status == 'removed':
            fact = ('雙腳赤腳' if kind == 'Feet' else names[kind] + '已無' + label)
            facts.append(fact + f'（{label}已卸除）')
        elif status == 'unfastened':
            facts.append(f'{names[kind]}的{label}已解開，尚未移除')
        else:
            facts.append(f'{names[kind]}穿著{label}')
    return ('- 【Python當前狀態：既定外觀，非新增動作】'
            + '；'.join(facts) + '。以下拍攝沿用此狀態；只有本段明確指定的事件可改變，'
            '已移除物品不重新出現，也不重演移除過程。')


def _fixed_reference_with_python_priority(fixed_setup, event):
    """Remove superseded opening-wardrobe facts, not reference identities.

    Only slots with a populated Python state take this path. Untracked
    appearance properties continue to fall back to the original reference.
    """
    match = re.search(
        r'(?s)^CURRENT_ACTOR_STATE[^\n]*\n(.*?)\nEXPECTED_ACTOR_STATE_AFTER_THIS_CLIP',
        event)
    if not match:
        return fixed_setup
    known = [line.strip() for line in match.group(1).splitlines()
             if re.match(r'^- (?:Torso|Bottom|Feet): ', line)]
    if not known:
        return fixed_setup
    # Bind identity to the reference, but never bind today's clothing to the
    # reference's historic opening wardrobe.
    fixed_setup = fixed_setup.replace(
        '與開場服裝依照參考圖片',
        '依照參考圖片；開場服裝僅是初始造型，不代表本段外觀')
    output = []
    opening = False
    for line in fixed_setup.splitlines():
        stripped = line.strip().lstrip('-* ').strip()
        opener = re.match(r'^(開場穿著|初始穿著|初始服裝|開場服裝)\s*[：:]\s*(.*)$',
                          stripped)
        if opener:
            opening = True
            output.append('初始服裝僅作歷史參考；本段已記錄的屬性由 Python 當前狀態決定。')
            inline = opener.group(2).strip()
            if inline and not any(inline in entry for entry in known):
                output.append(inline)
            continue
        if opening:
            if (not stripped or stripped.endswith(('：', ':')) or
                    stripped.startswith(('服裝依', '已卸除', '不重新', '人物', '整體',
                                         '故事', '演唱', '攝影', '後半段'))):
                opening = False
            elif any(stripped in entry for entry in known):
                # The Python-ledger category is known; discard the stale
                # reference outfit for this category. Other items stay.
                continue
        output.append(line)
    return '\n'.join(output)
