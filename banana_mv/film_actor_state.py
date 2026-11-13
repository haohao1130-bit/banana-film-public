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
