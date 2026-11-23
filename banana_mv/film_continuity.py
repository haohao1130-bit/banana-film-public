"""Five delivered-frame motion guides using pinned native MiniMaxH3AddGuide.

Re-encode RGB tails with the selected video VAE; this is not saved latent recovery.
The guide occupies the generated prefix, not a reference-picture identity slot.
"""
import hashlib
import math
import re
from fractions import Fraction
from pathlib import Path
import shutil

from banana_mv.core import FPS, command, probe

CONTEXT_FRAMES = 5


def previous_clip_index(seg):
    index = seg.get('kitchen_previous', seg['index'] - 1)
    return index if index is not None and index >= 0 else None


def _opening_field(brief, *labels):
    names = '|'.join(map(re.escape, labels))
    match = re.search(rf'(?m)^(?:{names})[：:][ \t]*\n?[ \t]*([^\n]+)', brief)
    return match[1].strip() if match else ''


def opens_with_cut(job, seg):
    """Read a cut from the opening commission, never from a later shot."""
    previous = previous_clip_index(seg)
    req = job['request']
    if previous is None or req.get('manual_h3') or req.get('mode') not in ('chain', 'chain5'):
        return False
    if seg.get('starts_with_cut'):
        return True
    brief = seg.get('director_plan', {}).get('event', '')
    opening = _opening_field(brief, '當段開場狀態', '開場', '承接')
    first_shot = re.search(
        r'(?im)^(?:SHOT\s+0?1(?:[ \t]*[（(][^）)\n]*[）)])?'
        r'|0(?:\.0+)?[ \t]*[–—-][^：:\n]+秒)[ \t]*[：:][ \t]*(.+)',
        brief,
    )
    cut_pattern = (r'^(?:(?:稍後|翌日|隔天|次日|下一刻)[，、, ]*|'
                   r'(?:開場|一開始|首鏡|第一鏡)(?:直接|就)?[：:，、, ]*)?'
                   r'(?:硬切|跳切|切(?:到|至|回|入|往)|轉場(?:到|至|回|進|[：:])|'
                   r'cut\s+to\b|hard\s+cut\b)')
    inputs = [opening, first_shot[1] if first_shot else '', brief.lstrip().split('\n', 1)[0]]
    if any(re.match(cut_pattern, line, re.I) for line in inputs):
        return True
    segments = job.get('segments', [])
    if not opening or previous >= len(segments):
        return False
    preceding = segments[previous].get('director_plan', {}).get('event', '')
    here = re.split(r'[，,：:。；;]', _opening_field(brief, '當段場景', '場景'))[0]
    there = re.split(r'[，,：:。；;]', _opening_field(preceding, '當段場景', '場景'))[0]
    if not here or not there or here in there or there in here:
        return False
    # An already-arrived character plus a new named location signals an edit;
    # a new camera angle or a later instruction to walk there does not.
    destination = re.match(r'^[^，。；！？]{0,16}?(?:坐到|回到|抵達|已(?:經)?(?:坐在|站在))([^，。；！？]+)', opening)
    return bool(destination and len(here) >= 3 and here[:3] in destination[1] and here[:3] not in there)


def motion_prefix(job, seg):
    return CONTEXT_FRAMES if (job['request'].get('production') == 'film'
        and job['request'].get('mode') == 'chain5' and previous_clip_index(seg) is not None
        and not opens_with_cut(job, seg)) else 0


def opening_render_frames(job, seg):
    if job['request'].get('mode') == 'chain5' and opens_with_cut(job, seg):
        return render_frames(seg['frames'], prefix_frames=0)
    return seg['model_frames']


def render_frames(delivered_frames, *, prefix_frames=CONTEXT_FRAMES):
    return 5+17*math.ceil((delivered_frames+prefix_frames-5)/17)


def fit_chain5_delivery(job, seg, prefix):
    """末五幀段的交付長度往下取到 H3 拍得出來的長度，H3 拍的每一格都用上、尾巴不裁。

    H3 只能拍 5+17k 格。10 秒要「5 格前導＋240 格」＝245 格，不合法，以前只好拍 260 格
    再把尾巴 0.625 秒裁掉，H3 排在最後的動作和聲音就被切了（實測 cf9f52c7f21f）。
    改拍 243 格、交付 238 格（9.92 秒）。後面各段起點與全片長度跟著縮。
    """
    if not prefix or seg.get('status') == 'done':
        return False
    legal = 5 + 17 * ((seg['frames'] + prefix - 5) // 17)
    frames = legal - prefix
    if legal < 124 or frames < 1 or (frames, seg.get('model_frames')) == (seg['frames'], legal):
        return False
    delta = seg['frames'] - frames
    start = seg.get('start_frame', 0)
    seg.setdefault('chain5_requested_frames', seg['frames'])
    seg.update(frames=frames, seconds=frames / FPS, model_frames=legal)
    for other in job['segments']:
        if other is not seg and other.get('start_frame', -1) > start:
            other['start_frame'] -= delta
            other['start'] = other['start_frame'] / FPS
    if job.get('duration'):
        job['duration'] = max(job['duration'] - delta / FPS, frames / FPS)
    return True


def prepare_motion_tail(source, destination, input_dir, stem):
    """Take exactly the last five delivered frames, preserving chronological order."""
    source=Path(source);destination=Path(destination);input_dir=Path(input_dir) if input_dir is not None else None
    stream=next(s for s in probe(source)['streams'] if s['codec_type']=='video')
    count=int(stream['nb_frames'])
    if count<CONTEXT_FRAMES or Fraction(stream['avg_frame_rate'])!=FPS:
        raise ValueError('末五幀接續需要至少五幀、24fps 的已完成片段。')
    with source.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    destination.mkdir(parents=True,exist_ok=True)
    names=[f'{stem}_{i:02d}.png' for i in range(CONTEXT_FRAMES)]
    for name in names:(destination/name).unlink(missing_ok=True)
    command(['ffmpeg','-y','-v','error','-i',source,'-vf',
             f'trim=start_frame={count-CONTEXT_FRAMES}:end_frame={count},setpts=PTS-STARTPTS',
             '-frames:v',str(CONTEXT_FRAMES),'-fps_mode','passthrough','-start_number','0',
             destination/(stem+'_%02d.png')])
    if not all((destination/name).is_file() for name in names):
        raise ValueError('末五幀擷取不完整，未送出下一段。')
    if input_dir is not None:
        input_dir.mkdir(parents=True,exist_ok=True)
        for name in names:shutil.copyfile(destination/name,input_dir/name)
    return names,{'kind':'rgb_reencoded_motion_guide','frames':CONTEXT_FRAMES,
                  'source_file':source.name,'source_sha256':digest,
                  'source_frame_interval':[count-CONTEXT_FRAMES,count]}


def upload_motion_tail(cfg, source, destination, stem):
    from banana_mv.services import upload_comfy_image
    names, receipt = prepare_motion_tail(source, destination, None, stem)
    return [upload_comfy_image(cfg, name, (destination/name).read_bytes(), 'image/png')
            for name in names], receipt


def add_motion_guide(graph, names, delivered_frames):
    """Preserve Ref2VA conditioning and references, append a native five-frame guide."""
    if len(names)!=CONTEXT_FRAMES or len(set(names))!=CONTEXT_FRAMES:
        raise ValueError('動作接續必須連接五個不同且有序的影格檔。')
    if graph['7']['class_type']!='MiniMaxH3ReferenceToVideo':
        raise ValueError('末五幀接續只適用短片原生 Ref2VA。')
    if '17' in graph:raise ValueError('末五幀不可同時當成單張首幀參考。')
    graph['7']['inputs']['length']=render_frames(delivered_frames)
    for i,name in enumerate(names):
        graph[f'motion_frame_{i}']={'class_type':'LoadImage','inputs':{'image':name}}
    batch=['motion_frame_0',0]
    for i in range(1,CONTEXT_FRAMES):
        key=f'motion_batch_{i}'
        graph[key]={'class_type':'ImageBatch','inputs':{'image1':batch,'image2':[f'motion_frame_{i}',0]}}
        batch=[key,0]
    original=graph['9']['inputs']['conditioning']
    graph['motion_guide']={'class_type':'MiniMaxH3AddGuide','inputs':{
        'positive':original,'latent':['7',1],'vae':['3',0],'image':batch,'frame_idx':0}}
    graph['9']['inputs']['conditioning']=['motion_guide',0]
    return graph


def preflight_nodes():
    return {name:{'class_type':kind,'inputs':{}} for name,kind in
            [('motion_guide','MiniMaxH3AddGuide'),('motion_batch','ImageBatch')]}
