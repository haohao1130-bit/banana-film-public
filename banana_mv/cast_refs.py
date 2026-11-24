"""蕉彌鐵板燒：替沒有提示圖的新角色補一張外觀參考圖。

共同設定寫了「S6＝白髮老人靈魂」卻沒有 <Picture N> 的角色，每段只靠文字，
H3 每次可能長得不一樣。這裡提供兩種補圖方式（都由 Python 執行，不經 9B）：

A. frame  ：角色第一次出場的那段拍完後，依 H3 全咒找出他最單獨入鏡的鏡頭，抽一格。
B. fitting：開炒前先用 H3 拍一段約 5 秒的單人定裝影片，抽一格。

補到的圖接在現有圖片後面（舊編號不變），並在共同設定加一行
「<Picture K>＝名稱＝Sx（外觀參考：…）」，後面的段就會把它當成這個角色的長相。
H3 一次最多 9 張圖；首尾幀模式要留 1 張給上一段末幀。
"""
import hashlib
import re
import shutil

from banana_mv.core import FPS, MAX_PICTURES

_DEFINE = re.compile(r'(?m)^[ \t]*(?:[-*•][ \t]*)?(S[1-8])[ \t]*[=＝][ \t]*([^\s=＝，,。；;：:（(]+)[^\n]*$')
_BOUND = re.compile(r'<Picture (\d+)>[ \t]*[=＝][ \t]*[^\s=＝，,。；;（(]+[ \t]*[=＝][ \t]*(S[1-8])(?![0-9])', re.I)
_SUBJECT_LINE = re.compile(r'(?m)^[ \t]*<Subject (\d+)>[^\n]*')
_SHOT = re.compile(r'\[Shot\s+(\d+)\]')
_SHOT_TIME = re.compile(r'\A\s*At\s+(\d{1,2}):(\d{2}(?:\.\d+)?)')
_CLOSE = re.compile(r'close-up|close up|medium close|frontal|portrait|特寫|近景', re.I)
_STYLE = re.compile(r'動畫|寫實|真人|3D|2D|畫風|anime|animation|photoreal', re.I)
_SUFFIX = re.compile(r'(?:的)?(?:靈魂|鬼魂|幽靈|靈)$')


def role_pattern(role):
    return re.compile(rf'(?<![A-Za-z0-9]){re.escape(role)}(?![0-9])', re.I)


def bound_roles(shared):
    return {role.upper() for _, role in _BOUND.findall(shared or '')}


def unbound_cast(shared):
    """共同設定裡有 S 代號定義、卻沒有綁 <Picture N> 的角色（依出現順序）。"""
    shared = shared or ''
    bound = bound_roles(shared)
    lines = shared.splitlines()
    found, seen = [], set()
    for match in _DEFINE.finditer(shared):
        role = match[1].upper()
        if role in bound or role in seen or '<Picture' in match[0]:
            continue
        seen.add(role)
        index = shared[:match.start()].count('\n')
        description = []
        for line in lines[index + 1:index + 6]:
            if not line.strip() or _DEFINE.match(line) or line.lstrip().startswith('■'):
                break
            description.append(line.strip())
        found.append({'role': role, 'name': match[2].strip(), 'description': ' '.join(description)})
    return found


def named(character, line):
    """9B 常把「白髮老人靈魂」寫成「白髮老人」：比對去掉字尾的核心名稱與它的三字片段。"""
    if mentioned(character['role'], line) or character['name'] in line:
        return True
    core = _SUFFIX.sub('', character['name']) or character['name']
    if len(core) >= 2 and core in line:
        return True
    return len(core) >= 3 and any(core[i:i + 3] in line for i in range(len(core) - 2))


def free_slots(job):
    reserve = 1 if job['request'].get('mode') == 'chain' else 0
    return max(0, MAX_PICTURES - reserve - len(job['images_comfy']))


def mentioned(role, text):
    text = re.sub(r'「[^」\n]*」|『[^』\n]*』', '「」', text or '')     # 台詞裡提到的名字不算出場
    return bool(role_pattern(role).search(text))


def add_reference(app, cfg, job, originals, character, image, source, segment=None):
    """把圖接到參考圖最後面，更新共同設定與還沒拍的段。回傳新的圖片編號。"""
    from banana_mv.film import kitchen_absent_pictures
    work = app.job_dir(job['id'])
    number = len(job['images_comfy']) + 1
    relative = f'sources/image_{number - 1}_cast_{character["role"].lower()}.png'
    target = app.backend.safe_child(work, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(image, target)
    uploaded = app.backend.upload_comfy_image(
        cfg, f'banana_film_{job["id"]}_{number - 1}.png', target.read_bytes(), 'image/png')
    job['sources']['images'].append(relative)
    job['images_comfy'].append(uploaded)
    originals.append(target)
    label = '定裝照' if source == 'fitting' else f'第 {segment + 1} 段畫面'
    line = f'<Picture {number}>＝{character["name"]}＝{character["role"]}（外觀參考：{label}，之後照這張的長相與服裝）'
    job['shared_setup'] = (job.get('shared_setup') or '').rstrip() + '\n' + line
    for seg in job['segments']:
        if seg.get('status') == 'done':
            continue
        seg['fixed_reference_settings'] = job['shared_setup']
        if 'absent_cast_pictures' in seg:
            seg['absent_cast_pictures'] = sorted(
                kitchen_absent_pictures(seg['director_plan']['event'], job['shared_setup']))
        if mentioned(character['role'], seg['director_plan']['event']):
            seg['refresh_prompt'] = True
    record = {'role': character['role'], 'name': character['name'], 'picture': number,
              'image_index': number - 1, 'source': source,
              'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}
    if segment is not None:
        record['segment'] = segment
    job.setdefault('cast_refs', []).append(record)
    return number


def _sections(prompt):
    def section(name, following):
        match = re.search(rf'(?ms)^[ \t]*{name}[ \t]*:(.*?)(?=^[ \t]*{following}[ \t]*:|\Z)', prompt)
        return match[1] if match else ''
    return (section('subject_definitions', 'summary'),
            section('detailed_description', 'overall_soundscape'))


def best_shot(prompt, character, seconds):
    """回傳角色最單獨入鏡那個鏡頭的取樣時間（秒），找不到回傳 None。"""
    definitions, details = _sections(prompt)
    subjects = {int(n): line for n, line in
                ((m[1], m[0]) for m in _SUBJECT_LINE.finditer(definitions))}
    own = {n for n, line in subjects.items() if named(character, line)}
    if not own:
        return None
    shots = list(_SHOT.finditer(details))
    best = None
    for index, shot in enumerate(shots):
        body = details[shot.end():shots[index + 1].start() if index + 1 < len(shots) else len(details)]
        tags = {int(n) for n in re.findall(r'<Subject (\d+)>', body)}
        if not tags & own:
            continue
        clock = _SHOT_TIME.match(body)
        start = int(clock[1]) * 60 + float(clock[2]) if clock else (0.0 if index == 0 else None)
        if start is None:
            continue
        following = _SHOT_TIME.match(details[shots[index + 1].end():]) if index + 1 < len(shots) else None
        end = int(following[1]) * 60 + float(following[2]) if following else seconds
        others = len(tags - own)
        score = (others, 0 if _CLOSE.search(body) else 1, -(end - start))
        if best is None or score < best[0]:
            best = (score, start, end)
    if best is None:
        return None
    _, start, end = best
    return min(max(start + 0.45 * max(end - start, 0.0), 0.2), max(seconds - 0.2, 0.2))


def grab_from_clip(app, cfg, job, seg, part, prompt, originals, command):
    """A：段拍完後，替這段第一次出場、還沒有圖的角色抽一格當提示圖。"""
    if not job['request'].get('auto_cast_frames') or not prompt:
        return []
    added = []
    for character in unbound_cast(job.get('shared_setup')):
        if free_slots(job) < 1:
            break
        if not mentioned(character['role'], seg['director_plan']['event']):
            continue
        moment = best_shot(prompt, character, seg['seconds'])
        if moment is None:
            continue
        frame = app.job_dir(job['id']) / f'{seg["index"]:02d}_cast_{character["role"].lower()}.png'
        command(['ffmpeg', '-y', '-v', 'error', '-ss', f'{moment:.3f}', '-i', str(part),
                 '-frames:v', '1', str(frame)])
        if not frame.is_file():
            continue
        added.append(add_reference(app, cfg, job, originals, character, frame, 'frame', seg['index']))
    return added


_GHOST = re.compile(r'半透明|透明|靈魂|幽靈|鬼魂|亡魂|冤魂|translucent|transparent|ghost|spirit', re.I)


def fitting_prompt(character, shared):
    style = ' '.join(line.strip() for line in (shared or '').splitlines()
                     if _STYLE.search(line) and '<Picture' not in line)[:400]
    description = character['description'] or character['name']
    if _GHOST.search(f"{character['name']} {description}"):
        # 半透明角色站在素色背景前看不出透明感，H3 會拍成實體：改用有景物的背景，並用英文明講要透出背景。
        look = ("<Subject 1> is a translucent ghost: the whole body, face, hair and clothing are semi-transparent, "
                "and the background is clearly visible through the body.")
        summary = ("A short character fitting shot: translucent <Subject 1> stands alone in a softly lit room with "
                   "wooden furniture and warm lamps behind, which show through the semi-transparent body.")
        shot = ("[Shot 1] A steady frontal medium shot of translucent <Subject 1> alone, centered, face and upper "
                "body in frame, soft warm light, a room with wooden furniture and lamps behind that stays visible "
                "through the semi-transparent body. " + look + " <Subject 1> stands still and looks into the camera "
                "with a calm, natural expression, then turns slightly to a three-quarter view and back to face the "
                "camera. No other people, no props, no text.")
    else:
        summary = ("A short character fitting shot: <Subject 1> stands alone in front of a plain, softly lit "
                   "backdrop and faces the camera so the face, hair, body shape and clothing are clearly visible.")
        shot = ("[Shot 1] A steady frontal medium shot of <Subject 1> alone, centered, face and upper body fully in "
                "frame, even soft light, plain neutral background. <Subject 1> stands still and looks into the camera "
                "with a calm, natural expression, then turns slightly to a three-quarter view and back to face the "
                "camera. No other people, no props, no text.")
    return (
        f"subject_definitions:\n<Subject 1> is {character['name']} ({character['role']}), a character with no "
        f"reference image, created from this description: {description}\n\n"
        f"summary:\n{summary}\n\n"
        "retention_analysis:\n<Subject 1> (appears in [Shot 1]): newly created from the description; this exact "
        "look will be reused for later shots.\n\n"
        "detailed_description:\n"
        + (f"Visual style: {style}\n" if style else '')
        + shot + "\n\n"
        "overall_soundscape:\nQuiet room tone.\n\n"
        "non_diegetic_music:\nNone."
    )


FITTING_FRAMES = 124            # H3 最短合法長度，約 5.17 秒
FITTING_MOMENT = 1.2            # 剛站定、正面看鏡頭的時間點


def fitting(app, cfg, job, originals, command):
    """B：開炒前替這道菜會出場、還沒有圖的角色拍定裝照（已經有圖的角色不重拍）。"""
    req = job['request']
    if not req.get('cast_fitting'):
        return []
    briefs = '\n'.join(seg['director_plan']['event'] for seg in job['segments'] if seg.get('status') != 'done')
    cast = [c for c in unbound_cast(job.get('shared_setup')) if mentioned(c['role'], briefs)]
    cast.sort(key=lambda c: role_pattern(c['role']).search(briefs).start())
    work = app.job_dir(job['id'])
    added = []
    for count, character in enumerate(cast, 1):
        if free_slots(job) < 1:
            break
        job['status'] = 'casting'
        job['cast_fitting_progress'] = {'role': character['role'], 'name': character['name'],
                                        'index': count, 'total': len(cast)}
        app.write_state(job)
        prompt = fitting_prompt(character, job.get('shared_setup'))
        graph = app.build_workflow([], None, *job['size'], FITTING_FRAMES, prompt,
                                   (job['seed'] + 7919 * count) % (2 ** 48), None,
                                   **app.graph_options(req, FITTING_FRAMES / FPS, {'director_mode': 'story'}))
        stem = f'cast_{character["role"].lower()}'
        graph['16']['inputs']['filename_prefix'] = f'BananaFilm/{job["id"]}/{stem}'
        app.preflight(cfg, graph)
        entry = app.wait_generation(cfg, app.backend.queue_prompt(cfg, graph), job)
        video = work / f'{stem}_fitting.mp4'
        app.backend.comfy_download(cfg, app.video_info(entry), video)
        frame = work / f'{stem}_fitting.png'
        command(['ffmpeg', '-y', '-v', 'error', '-ss', f'{FITTING_MOMENT:.3f}', '-i', str(video),
                 '-frames:v', '1', str(frame)])
        if frame.is_file():
            added.append(add_reference(app, cfg, job, originals, character, frame, 'fitting'))
        app.write_state(job)
    job.pop('cast_fitting_progress', None)
    return added
