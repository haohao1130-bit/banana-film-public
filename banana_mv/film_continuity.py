"""Five delivered-frame motion guides using pinned native MiniMaxH3AddGuide.

Re-encode RGB tails with the selected video VAE; this is not saved latent recovery.
The guide occupies the generated prefix, not a reference-picture identity slot.
"""
import hashlib
import math
from fractions import Fraction
from pathlib import Path
import shutil

from banana_mv.core import FPS, command, probe

CONTEXT_FRAMES = 5


def motion_prefix(job, seg):
    return CONTEXT_FRAMES if (job['request'].get('production')=='film'
        and job['request'].get('mode')=='chain5' and seg['index']>0) else 0


def render_frames(delivered_frames):
    return 5+17*math.ceil((delivered_frames+CONTEXT_FRAMES-5)/17)


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
