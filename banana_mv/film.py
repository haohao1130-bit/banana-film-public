"""Story-first short films. One upstream plan, isolated native H3 shot writers."""
import copy
import hashlib
import json
import math
from pathlib import Path
import random
import re
import shutil
import threading
import time
import uuid

from banana_mv import server as app, masters
from banana_mv.core import FPS, dimensions, output_dimensions, map_image_mentions, reference_images
from banana_mv.film_media import trim_native, require_audio
from banana_mv.scene_state import parse_object, rewrite_retry_count, atomic_json
from banana_mv.shoot_plan import _pictures, _text, CLIP_INTENSITY

PLANNER = """You are the screenwriter and director of a short film, not a music video.
Read the user's story and references, develop a compelling complete film within the
supplied duration contract. With duration_policy='target', develop the story for
target_seconds and deliver at least minimum_duration_seconds without exceeding
max_seconds. Expand causal actions, obstacles, choices, consequences and motivated
listener/emotional reactions within the user's premise; preserve identities, required
lines and outcome. Allocate believable performance time before dividing into clips.
Do not merely inflate seconds, repeat events, add unrelated incidents or hold an
already completed ending. With no target contract, choose a natural finished length
within max_seconds; FAITHFUL never invents plot or dialogue to fill time.
Honor adaptation: FAITHFUL permits camera/staging decisions but no new plot or dialogue; AUTO permits creative development within explicit requirements. Genres are tone, not permission to replace the premise.
Preserve the user's identities, world, causal backbone and required outcome. Develop
staging, motivations, reactions and dialogue where permitted; do not mechanically
illustrate every sentence. Plan expressive performances and purposeful scene changes.
Give each clip a dramatic purpose: what changes in the situation, relationship or
viewer's understanding between its opening and ending. Express that change through
visible behavior, not an explanatory synopsis. Choose progression appropriate to the
story: comedy, intimacy, suspense, action or quiet drama need different rhythms; do
not force every film into a trailer-style escalation/reveal formula.
Budget duration for dialogue delivery, physical action, listener response and any
meaningful pause together. Preserve required lines verbatim; when they do not fit,
redistribute events across clips within the ceiling rather than silently dropping
lines or demanding unnaturally fast speech. Do not fill leftover seconds with an
arbitrary freeze or premature final pose. A pause must belong to the current event.
Each event happens once. At every clip boundary, compare the outgoing state with
the next opening: actor positions, facing/eyelines, held objects, completed actions
and emotional intensity. Carry current consequences into the next local brief;
do not restart an exchange. The final clip earns and completes the ending.
sound='ambient' means no speech, dialogue or vocals. sound='dialogue' permits concise
dialogue as the story requires. Use environmental sound and effects; add a score
only when explicitly requested by the story, not an obligatory background song.
The next director sees ONLY one brief, the reference images, its duration and local
sound rules. Each brief must be self-contained: original <Picture N> identity bindings,
current location and props, opening situation, local events, current emotions, any exact
dialogue and speaker, sound/voice description, and the required local ending state.
Naturally include the local dramatic purpose, who approaches or withdraws, who looks
at whom, object handoffs, and the response needed for the event to register. Mention
only relationships relevant to this clip; do not force absent actors into coverage.
Carry only current facts, no whole-story recap, future events, or ending previews.
Reference images fix identity, not expressions, pose or eye state; unused references
do not require a character to appear. Keep dialogue short enough to finish within the
clip. Use only reference_count connected images; when it is zero, design actors and
places from the story without any <Picture N> tags. Do not split a spoken sentence
at a clip boundary. When no dialogue is requested,
use physical storytelling and environmental sound, not obligatory speech.
Extract shared_setup as FIXED REFERENCE SETTINGS for every local director.
Include explicit original name/role-to-<Picture N> bindings for every connected
reference, fixed world/geography and requested original supporting character designs.
Preserve names, roles and separate locations; do not reassign actors by appearance.
A reference showing a person defines the WHOLE named actor, even in a full-body,
costume or multi-view sheet. Clothing and body parts are attributes, not substitute
subjects that leave the wearer unnamed or their head implicitly unseen.
These settings identify references, not a mandatory attendance list. Keep plot
chronology, future events, the requested outcome and final shot OUT of shared_setup.
Each local brief also names its active actors with their bound <Picture N> tags.
Current clip states override reference expressions/poses and changed clothing.
Keep briefs concise and executable. No camera shot list here; the local director
chooses coverage. Reply ONLY valid JSON:
{"title":"film title","shared_setup":"fixed reference identities and world, no plot chronology","segments":[{"seconds":10,"mode":"story",
"brief":"self-contained local shooting commission"}]}.
Each seconds is between 5.2 and max_clip_seconds, total no greater than max_seconds.
mode is story or action. Every segment has a different progressing purpose."""

WRITER = """Enhance ONE local film commission into a native MiniMax H3 ref2va prompt.
Follow the supplied guide's output sections, but there is NO source audio or song.
All sound is generated: describe environmental sound, effects and optional score in
the sound sections. Do not reference <Audio N>, <Video N>, audio reuse, fully_copy or
source-song lip sync. Use only connected <Picture N> references. Honor fixed_reference_settings as the
binding authority: names and roles stay attached to their assigned images. Never
replace an absent actor with another supplied reference or infer a new role from
image order. Original supporting actors may appear without invented Picture IDs.
Fixed settings identify assets; the current commission chooses who is present.
For corrections, these bindings remain authoritative even if an older original_prompt
misassigned an actor. Preserve unchanged events without preserving wrong identities.
Keep current expressions, blocking and clothing changes from this clip, not static
reference poses. Cast does not have
to attend merely because a picture was provided. No new plot beyond this commission.
Invent strong cinematic coverage: every Shot has a concrete viewpoint, shot size,
composition, spatial depth, motivated movement, light and visible action timing.
Use inserts, reactions, contrast and action-matched cuts when they clarify or intensify
the event; hold complete action or emotional/comic pauses when they need time. A clip
is not one mandatory long take. Do not mechanically rotate camera examples or zoom
instead of cutting. Preserve position, direction and object state across cuts.
Define each referenced person as the whole named character in subject_definitions;
describe their outfit as an attribute. Never substitute a skirt, torso or disembodied
hands for the acting person or label the wearer unseen merely to describe clothing.
Reference appearance is identity, not fixed expression, pose, gaze or closed eyes.
For ordinary character coverage, frame the intended face and head clearly with
headroom and room for the assigned motion; reframe or track as actors move rather
than letting their heads drift off the top edge. Low angles still need a coherent
view of the intended subject. Match shot size, camera height and visible anatomy:
a tight face shot cannot also require a waist bow in that same tight frame.
Deliberate hand/foot/prop inserts or motivated extreme facial details may omit the
rest of the head; identify them as detail inserts, not the default portrayal of a
character. Do not turn an exchange into continuous torso/hand coverage when faces,
reactions or whole-body action carry the event. Choose coverage freely for the beat.
Translate the commissioned dramatic purpose into actor blocking and coverage:
make changes in distance, eyelines, object possession and emotional response visible.
Choose a two-person view, reverse angle, reaction or insert when it serves that change;
no mandatory shot count, alternating shot-size recipe or fixed cutting interval.
Use decisive camera work when the scene calls for it: state the camera's starting
position, movement relative to the actors and resulting reveal/composition. Distinguish
camera translation, rotation and lens zoom; avoid incompatible simultaneous directions.
Direct emotion through visible face and body behavior, with reactions that develop
from the preceding action rather than a reference-sheet expression held throughout.
When dialogue is permitted, preserve the assigned speaker and exact local text, make
the speaking face readable, and describe voice/delivery and mouth movement. Do not
add lines unless the commission requests them. Budget speech, action and listener
response within the same duration; a response may overlap speech naturally. Keep
speaker identity and eyelines clear across cuts, and do not restart a line on a new
angle. End dialogue before the clip ends without rushing or dropping assigned words.
Allow a motivated emotional/comic pause; do not end the event early and mechanically
hold a final pose. Preserve the commissioned local end state without previewing later
plot. Internal cuts are staging intentions, not guaranteed frame-accurate edit commands.
No subtitles or text overlays unless the user explicitly requested them. Shot times
are clip-local and fit the duration. sound_mode='ambient' prohibits speech, dialogue,
vocals and singing. No background score unless the commission explicitly calls for it.
For a local correction preserve unrequested events, identity, dialogue and the ending;
rewrite the full prompt, not a diff. Output only the final filming prompt."""

GENRES={'comedy':'搞笑','cinematic':'電影','drama':'戲劇','action':'武打',
        'romance':'愛情','bl':'BL／男男愛情','sports':'運動','scifi':'科幻','horror':'懸疑恐怖'}


def slot_map(req):
    slots=req.get('image_slots')
    if slots is None:return {i+1:i+1 for i in range(len(req.get('image_ids',[])))}
    return {i+1:sum(x is not None for x in slots[:i+1]) for i,x in enumerate(slots) if x is not None}


def map_story(req,text,count):
    if req.get('image_slots') is None:return map_image_mentions(text,count)
    mapping=slot_map(req)
    def replace(m):
        number=int(m[1])
        if number not in mapping:raise ValueError(f'@圖片{number} 是空格，請在該格選圖。')
        return f'<Picture {mapping[number]}>'
    return re.sub(r'@(?:圖片|图片|image)\s*(\d+)',replace,text,flags=re.I)


def review_draft(job):
    reverse={v:k for k,v in slot_map(job['request']).items()}
    def label(text):
        return re.sub(r'<Picture (\d+)>',lambda m:'@圖片'+str(reverse.get(int(m[1]),int(m[1]))),text)
    return {'title':job['title'],'segments':[{'seconds':s['seconds'],'mode':s['director_mode'],
            'brief':label(s['director_plan']['event'])} for s in job['segments']]}


def normalize_prompt(text,count):
    text=_text(text).strip()
    if not text:raise ValueError('短片提示詞為空。')
    if re.search(r'<\s*(?:Audio|Video)\s*\d+\s*>',text,re.I):
        raise ValueError('短片未連接參考音訊或影片，提示詞不可引用 Audio／Video 標籤。')
    def checked(m):
        n=int(m[1])
        if not 1<=n<=count:raise ValueError('短片提示詞引用未連接的圖片。')
        return f'<Picture {n}>'
    return re.sub(r'<\s*(?:Picture|Image)\s*(\d+)\s*>',checked,text,flags=re.I)


def validate_plan(raw,req,image_count):
    data=parse_object(_text(raw));rows=data.get('segments')
    if not isinstance(rows,list) or not 1<=len(rows)<=34:raise ValueError('短片需有 1–34 段。')
    shared=data.get('shared_setup','')
    if not isinstance(shared,str) or len(shared)>12000:
        raise ValueError('共用角色與場景設定需為文字，最多 12000 字。')
    shared=map_story(req,shared.strip(),image_count)
    normalize_prompt(shared,image_count) if shared else None
    if req.get('fixed_reference_version')==1:
        if not shared:raise ValueError('缺少 shared_setup 共用角色表與固定場景設定。')
        missing=[i for i in range(1,image_count+1) if f'<Picture {i}>' not in shared]
        if missing:raise ValueError('共用角色表漏掉圖片綁定：'+', '.join(map(str,missing)))
    result=[];start=0;seen=set()
    for i,row in enumerate(rows):
        if not isinstance(row,dict):raise ValueError('每個短片段落需為物件。')
        seconds=row.get('seconds');mode=row.get('mode','story');brief=row.get('brief')
        if isinstance(seconds,bool) or not isinstance(seconds,(int,float)) or not math.isfinite(seconds):
            raise ValueError('每段 seconds 需為有限數字。')
        # With no external soundtrack, use the model's exact AV frame grid rather
        # than generating a longer utterance and chopping off its last syllable.
        requested=round(seconds*FPS)
        frames=5+((requested-5)//17)*17
        if seconds<124/FPS-1e-8 or seconds>req['segment_seconds']+1e-8 or frames<124:
            raise ValueError('每段需介於 5.2 秒與所選分段上限。')
        if mode not in ('story','action') or not isinstance(brief,str) or not 20<=len(brief.strip())<=5000:
            raise ValueError('每段需有 story/action 模式及完整當段委託。')
        brief=map_story(req,brief,image_count)
        normalize_prompt(brief,image_count)
        key=re.sub(r'\s+','',brief)
        if key in seen:raise ValueError('短片重複完整事件，請推進故事而非複製段落。')
        seen.add(key)
        result.append({'index':i,'start_frame':start,'frames':frames,'start':start/FPS,
                       'seconds':frames/FPS,'model_frames':frames,'status':'waiting',
                       'director_mode':mode,'director_plan':{'index':i,'mode':mode,'event':brief}})
        start+=frames
    if start>math.floor(req['max_seconds']*FPS):raise ValueError('導演規劃超過片長上限。')
    for seg in result:seg.update(song_seconds=start/FPS,segment_count=len(result),fixed_reference_settings=shared)
    return {'title':str(data.get('title') or '未命名短片')[:120],'duration':start/FPS,'segments':result,'shared_setup':shared}


def duration_contract(req):
    """Opt-in for new AUTO plans; respect achievable native AV frame totals."""
    if req.get('duration_policy')!='target' or not req.get('auto_director'):
        return {}
    limit=math.floor(req['max_seconds']*FPS)
    cap=5+((round(req['segment_seconds']*FPS)-5)//17)*17
    # Each clip has 124 + 17*k frames. Find the longest feasible whole film
    # under the ceiling, including short targets with 6-second clip caps.
    achievable=max(n*124+17*((min(limit,n*cap)-n*124)//17)
                    for n in range(1,35) if n*124<=limit)
    minimum=min(math.ceil(limit*.7),achievable)
    return {'duration_policy':'target','target_seconds':req['max_seconds'],
            'minimum_duration_seconds':minimum/FPS}


def validate_planned_duration(plan,req):
    contract=duration_contract(req)
    if contract and plan['duration']+1e-8<contract['minimum_duration_seconds']:
        raise ValueError(f"故事規劃過短：目標 {req['max_seconds']:g} 秒，實際 {plan['duration']:.3f} 秒，"
                         f"至少需 {contract['minimum_duration_seconds']:.3f} 秒。"
                         'Return to upstream story development: expand causal events, choices, '
                         'consequences and motivated reactions within the premise; preserve '
                         'required dialogue and outcome. Do not just increase seconds, repeat '
                         'events or pad the ending. Return the complete revised JSON.')


def plan_film(cfg,job,originals):
    work=app.job_dir(job['id']);path=work/'director_plan.json';req=job['request']
    source={'story':map_story(req,req['prompt'],len(originals)),
            'reference_count':len(originals),
            'max_seconds':req['max_seconds'],'max_clip_seconds':req['segment_seconds'],
            'style':req['visual_style'],'sound':req['sound_mode'],'intensity':req['intensity']}
    source.update(duration_contract(req))
    if 'auto_director' in req:
        source['adaptation']=('AUTO: creatively develop the premise, keeping explicit events, dialogue and outcome.'
                              if req['auto_director'] else 'FAITHFUL: organize and stage only the supplied events and dialogue; do not invent new plot or lines.')
        source['genres']=[GENRES[g] for g in req.get('genres',[])]
        source['reference_slots']={f'@圖片{k}':f'<Picture {v}>' for k,v in slot_map(req).items()}
    fingerprint=hashlib.sha256(json.dumps(source,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    if path.exists():
        saved=json.loads(path.read_text())
        if saved.get('input_sha256')!=fingerprint:raise ValueError('故事與已保存大綱不一致，請建立新作品。')
        verified=validate_plan(json.dumps({'title':saved['title'],'shared_setup':saved.get('shared_setup',''),'segments':[
            {'seconds':s['seconds'],'mode':s['director_mode'],'brief':s['director_plan']['event']}
            for s in saved['segments']]}),req,len(originals))
        if not saved.get('user_reviewed'):validate_planned_duration(verified,req)
        return verified
    parts=[('text',json.dumps(source,ensure_ascii=False))]+_pictures(originals)
    for attempt in range(req['rewrite_retries']+1):
        raw=app.backend.rewrite_local(cfg,PLANNER,parts,uuid.uuid4().hex[:8])
        (work/f'director_attempt_{attempt:02d}.txt').write_text(raw,encoding='utf-8')
        try:
            plan=validate_plan(raw,req,len(originals))
            validate_planned_duration(plan,req)
            atomic_json(path,dict(plan,input_sha256=fingerprint))
            return plan
        except (ValueError,TypeError,KeyError) as error:
            if attempt==req['rewrite_retries']:raise
            parts=[*parts,('text','Previous rejected draft:\n'+raw),
                   ('text','Correct the delivery and return the complete JSON only. Error: '+str(error))]


def write_prompt(cfg,job,seg,originals,tail=None,correction=None,base=None,dest=None,artifact_prefix=""):
    req=job['request'];offset=int(bool(tail));brief=seg['director_plan']['event']
    brief=re.sub(r'<Picture (\d+)>',lambda m:f'<Picture {int(m[1])+offset}>',brief)
    fixed=seg.get('fixed_reference_settings') or job.get('shared_setup','')
    if req.get('fixed_reference_version')==1 and not fixed:
        raise ValueError('當段缺少固定角色表與場景設定，請重新產生劇本。')
    fixed=re.sub(r'<Picture (\d+)>',lambda m:f'<Picture {int(m[1])+offset}>',fixed)
    task={'seconds':seg['seconds'],'style':req['visual_style'],'sound_mode':req['sound_mode'],
          'reference_count':len(originals)+offset,
          'current_clip_commission':brief}
    if fixed:task['fixed_reference_settings']=fixed
    if 'auto_director' in req:
        task['adaptation']='creative local staging' if req['auto_director'] else 'faithful staging; no new events or dialogue'
        task['genres']=[GENRES[g] for g in req.get('genres',[])]
    if req.get('mode')=='chain5' and seg['index']>0:
        task['motion_context']='The first five render frames continue the preceding clip and are trimmed before delivery. Continue its motion into this local event; do not replay the previous event. Context is not another actor or numbered Picture reference.'
    if tail:task['continuity_reference']='<Picture 1> is the previous last frame as visual reference, not a locked first frame or another actor.'
    if correction:task.update(original_prompt=base,local_correction=correction)
    text=json.dumps(task,ensure_ascii=False)
    guide=Path(cfg['guides']['ref']).read_text(encoding='utf-8')
    system=guide+'\n'+WRITER+'\n'+CLIP_INTENSITY[req['intensity']]
    refs=([tail] if tail else [])+list(originals)
    if dest:atomic_json(Path(dest)/(artifact_prefix+'repair_request.json'),{'system':system,'user':text})
    for attempt in range(req['rewrite_retries']+1):
        raw=app.backend.rewrite_local(cfg,system,[('text',text)]+_pictures(refs),uuid.uuid4().hex[:8])
        target=Path(dest) if dest else app.job_dir(job['id'])
        (target/(f'{artifact_prefix or str(seg["index"]).zfill(2)+"_"}rewrite_raw_{attempt:02d}.txt')).write_text(raw,encoding='utf-8')
        try:return normalize_prompt(raw,len(refs))
        except ValueError as error:
            if attempt==req['rewrite_retries']:raise
            text+='\nReturn corrected complete prompt. '+str(error)


def inputs(job,cfg):
    originals=[app.backend.safe_child(app.job_dir(job['id']),p) for p in job['sources']['images']]
    if not all(p.is_file() for p in originals):raise ValueError('角色參考素材遺失。')
    if len(originals)!=len(job['images_comfy']):raise ValueError('專案圖片數量不符。')
    inp=Path(cfg['comfy_input_dir']);inp.mkdir(parents=True,exist_ok=True)
    for source,name in zip(originals,job['images_comfy']):shutil.copyfile(source,app.backend.safe_child(inp,name))
    return originals,None,None


def start(req):
    cfg=copy.deepcopy(app.backend.load_config());req=dict(req)
    story=req.get('prompt','')
    if not isinstance(story,str) or not 1<=len(story.strip())<=30000:raise ValueError('請填寫故事，最多 30000 字。')
    maximum=req.get('max_seconds',60);chunk=req.get('segment_seconds',10)
    if isinstance(maximum,bool) or not isinstance(maximum,(int,float)) or not math.isfinite(maximum) or not 6<=maximum<=180:
        raise ValueError('片長上限為 6–180 秒。')
    if isinstance(chunk,bool) or not isinstance(chunk,(int,float)) or chunk not in (6,10,15):raise ValueError('分段上限請選 6、10 或 15 秒。')
    req.update(production='film',fixed_reference_version=1,max_seconds=float(maximum),segment_seconds=min(float(chunk),float(maximum)),
               sampling_steps=8,visual_style=req.get('visual_style','真人電影'),sound_mode=req.get('sound_mode','ambient'),
               rewrite=True,story_plan=True,project_scope='full',director=req.get('director','auto'))
    if req.get('mode','chain') not in ('independent','chain','chain5'):raise ValueError('未知連續性模式。')
    req.setdefault('mode','chain');req.setdefault('intensity','high')
    if req['intensity'] not in CLIP_INTENSITY:raise ValueError('未知攝影強度。')
    if req['visual_style'] not in ('真人電影','動畫','特攝','依故事決定'):raise ValueError('未知影像風格。')
    if req['sound_mode'] not in ('ambient','dialogue'):raise ValueError('未知聲音模式。')
    req['rewrite_retries']=rewrite_retry_count(req)
    req.setdefault('auto_director',True);req.setdefault('script_review',True)
    if not isinstance(req['auto_director'],bool) or not isinstance(req['script_review'],bool):
        raise ValueError('自動導演與劇本確認必須為勾選值。')
    req['duration_policy']='target' if req['auto_director'] else 'ceiling'
    genres=req.get('genres',[])
    if not isinstance(genres,list) or any(not isinstance(g,str) or g not in GENRES for g in genres):
        raise ValueError('請選擇有效題材。')
    req['genres']=list(dict.fromkeys(genres))
    if 'image_slots' in req:
        slots=req['image_slots']
        if not isinstance(slots,list) or len(slots)!=9 or any(x is not None and (not isinstance(x,str) or not x) for x in slots):
            raise ValueError('圖片需使用九個獨立格，空格填 null。')
        req['image_ids']=[x for x in slots if x is not None]
    ids=req.get('image_ids',[])
    if not isinstance(ids,list):raise ValueError('圖片素材需為清單。')
    if ids:ids=reference_images(ids,req['mode']=='chain')
    if req['mode']=='chain5':
        from banana_mv.film_continuity import preflight_nodes
        app.preflight(cfg,preflight_nodes())
    rows=[app.backend.asset(aid) for aid in ids]
    if any(r['kind']!='image' for r in rows):raise ValueError('角色／場景參考需為圖片。')
    originals=[app.backend.LIBRARY/r['file'] for r in rows]
    map_story(req,story,len(rows))
    size=dimensions(req.get('aspect','16:9'),req.get('width'));out=output_dimensions(req.get('aspect','16:9'),req.get('width'))
    if not Path(cfg['guides']['ref']).is_file():raise ValueError('請先執行 Colab ② 下載 9B 與原生指南。')
    app.preflight(cfg,{'encoder':{'class_type':'CLIPLoader','inputs':{'clip_name':cfg['rewriter']['model']}},
                       'generate':{'class_type':'TextGenerate','inputs':{}}})
    if not req['script_review']:
        app.preflight(cfg,app.build_workflow([r['comfy_name'] for r in rows],None,*size,124,'',0,
                                           **app.graph_options(req,6)))
    if not app.GPU_LOCK.acquire(blocking=False):raise ValueError('已有作品製作中，請先等它完成。')
    try:
        q=app.backend.comfy(cfg,'/queue')
        if q.get('queue_running') or q.get('queue_pending'):raise ValueError('ComfyUI 還有工作，請稍後再開拍。')
        seed=req.get('seed')
        if seed in ('',None):seed=random.randrange(2**48)
        if isinstance(seed,bool) or not str(seed).isdigit() or not 0<=int(seed)<2**48:raise ValueError('Seed 需為 0–281474976710655 的整數。')
        job_id=uuid.uuid4().hex[:12];work=app.RUNS/job_id;work.mkdir()
        source_dir=work/'sources';source_dir.mkdir();paths=[]
        for i,p in enumerate(originals):
            target=source_dir/f'image_{i}{p.suffix.lower()}';shutil.copyfile(p,target);paths.append(str(target.relative_to(work)))
        job={'id':job_id,'status':'planning_story','created':time.time(),'request':req,'duration':0,
             'segments':[],'size':size,'output_size':out,'seed':int(seed),'settings_version':2,
             'images_comfy':[r['comfy_name'] for r in rows],'sources':{'images':paths},
             'title':str(req.get('project_name') or '新短片')[:120],'timeline_source':'film_plan',
             'note':'H3 原生影音生成；未做 GPU 品質驗證，跨段聲線與音樂不保證一致。'}
        app.write_state(job)
        threading.Thread(target=worker,args=(job,cfg,*inputs(job,cfg)),daemon=True).start()
        return job
    except Exception:app.GPU_LOCK.release();raise


def save_script(job_id,draft,revision,render=False):
    """Only unrendered review drafts may change. Approval atomically starts rendering."""
    if not app.GPU_LOCK.acquire(blocking=False):raise ValueError('已有作品製作中，請稍後再確認劇本。')
    handed_off=False
    try:
        job=app.read_state(job_id)
        if job['request'].get('production')!='film' or job['status']!='script_ready':
            raise ValueError('只有尚未開拍的劇本草稿可以修改或確認。')
        if not isinstance(revision,str) or revision!=job.get('script_revision'):
            raise ValueError('劇本已有更新，請重新開啟作品後再確認，避免覆蓋新版。')
        if not isinstance(draft,dict):raise ValueError('缺少劇本。')
        plan=validate_plan(json.dumps(dict(draft,shared_setup=job.get('shared_setup','')),ensure_ascii=False),job['request'],len(job['images_comfy']))
        if any(s.get('prompt_id') or s.get('prompt') for s in job['segments']):
            raise ValueError('已有生成稿，請建立新作品而非覆寫劇本。')
        cfg=copy.deepcopy(app.backend.load_config())
        if render:
            queue=app.backend.comfy(cfg,'/queue')
            if queue.get('queue_running') or queue.get('queue_pending'):raise ValueError('ComfyUI 尚有工作，請稍後開拍。')
            app.preflight(cfg,app.build_workflow(job['images_comfy'],None,*job['size'],plan['segments'][0]['model_frames'],'',job['seed'],
                                               **app.graph_options(job['request'],plan['segments'][0]['seconds'],plan['segments'][0])))
        job.setdefault('script_history',[]).append({'revision':revision,'script':job.get('script_draft',review_draft(job)),'note':'確認開拍' if render else '手動儲存','created':time.time()})
        job.update(title=plan['title'],segments=plan['segments'],duration=plan['duration'],shared_setup=plan['shared_setup'],
                   script_revision=uuid.uuid4().hex,script_approved=render,resumed=time.time())
        job['script_draft']=review_draft(job)
        previous=json.loads((app.job_dir(job_id)/'director_plan.json').read_text())
        atomic_json(app.job_dir(job_id)/'director_plan.json',dict(plan,input_sha256=previous['input_sha256'],user_reviewed=True))
        if render:
            originals,_,_=inputs(job,cfg);job['status']='running';app.CANCEL.discard(job_id)
        app.write_state(job)
        if render:
            thread=threading.Thread(target=worker,args=(job,cfg,originals,None,None),daemon=True)
            try:thread.start();handed_off=True
            except Exception:
                job.update(status='script_ready',script_approved=False);app.write_state(job);raise
        return job
    finally:
        if not handed_off:app.GPU_LOCK.release()



def revise_script(job_id,draft,revision,instruction):
    """Revise the submitted current draft; never render or silently replace a newer draft."""
    if not isinstance(instruction,str) or not 1<=len(instruction.strip())<=3000:
        raise ValueError('請填寫劇本修改意見，最多 3000 字。')
    if not app.GPU_LOCK.acquire(blocking=False):raise ValueError('導演正在工作，請稍後再修稿。')
    try:
        job=app.read_state(job_id)
        if job['status']!='script_ready' or job['request'].get('production')!='film':
            raise ValueError('只有尚未開拍的劇本可以請導演細修。')
        if revision!=job.get('script_revision'):raise ValueError('劇本已有更新，請重新開啟作品。')
        req=job['request'];count=len(job['images_comfy'])
        current=validate_plan(json.dumps(dict(draft,shared_setup=job.get('shared_setup','')),ensure_ascii=False),req,count)
        instruction=map_story(req,instruction,count)
        cfg=copy.deepcopy(app.backend.load_config());originals,_,_=inputs(job,cfg)
        source={'original_story':map_story(req,req['prompt'],count),
                'fixed_reference_settings':current['shared_setup'],
                'current_script':{'title':current['title'],'segments':[
                    {'seconds':s['seconds'],'mode':s['director_mode'],'brief':s['director_plan']['event']} for s in current['segments']]},
                'revision_request':instruction,'max_seconds':req['max_seconds'],
                'max_clip_seconds':req['segment_seconds'],'sound':req['sound_mode'],
                'style':req['visual_style'],'intensity':req['intensity'],
                'reference_count':count,'genres':[GENRES[g] for g in req.get('genres',[])]}
        system=PLANNER+"\nREVISION TASK: Edit the CURRENT SCRIPT according to revision_request. Preserve the title and all unaffected scenes, dialogue, actor identities, causal order and outcome unless the revision explicitly asks to change them. Do not restart from the original story or apply unrelated creative expansion. Return the complete revised JSON using the same schema."
        parts=[('text',json.dumps(source,ensure_ascii=False))]+_pictures(originals)
        for attempt in range(req['rewrite_retries']+1):
            raw=app.backend.rewrite_local(cfg,system,parts,uuid.uuid4().hex[:8])
            (app.job_dir(job_id)/f'script_revision_{revision}_{attempt}.txt').write_text(raw,encoding='utf-8')
            try:
                plan=validate_plan(raw,req,count);break
            except (ValueError,TypeError,KeyError) as error:
                if attempt==req['rewrite_retries']:raise
                parts=[*parts,('text','Return corrected complete JSON. '+str(error))]
        history=job.setdefault('script_history',[])
        history.append({'revision':revision,'script':draft,'note':instruction,'created':time.time()})
        job.update(title=plan['title'],segments=plan['segments'],duration=plan['duration'],shared_setup=plan['shared_setup'],script_revision=uuid.uuid4().hex)
        job['script_draft']=review_draft(job)
        path=app.job_dir(job_id)/'director_plan.json';previous=json.loads(path.read_text())
        atomic_json(path,dict(plan,input_sha256=previous['input_sha256'],user_reviewed=True))
        app.write_state(job);return job
    finally:app.GPU_LOCK.release()

def worker(job,cfg,originals,song=None,drive=None):
    work=app.job_dir(job['id']);tail=None;motion_files=[]
    from banana_mv.film_continuity import motion_prefix,prepare_motion_tail,add_motion_guide
    try:
        if not job['segments']:
            job['status']='planning_story';app.write_state(job)
            plan=plan_film(cfg,job,originals)
            job.update(segments=plan['segments'],duration=plan['duration'],shared_setup=plan['shared_setup'])
            if not job['request'].get('project_name'):job['title']=plan['title']
            app.write_state(job)
        if job['request'].get('script_review') and not job.get('script_approved'):
            job.update(status='script_ready',script_revision=uuid.uuid4().hex)
            job['script_draft']=review_draft(job);app.write_state(job);return
        for seg in job['segments']:
            if job['id'] in app.CANCEL:job['status']='cancelled';app.write_state(job);return
            i=seg['index'];part=app.adopted_part(job,seg);job['current']=i+1
            if seg.get('takes') and not part.is_file():raise ValueError('採用版片段遺失，請恢復該版本或另選版本。')
            if seg.get('status')=='done' and app.valid_part(part,seg,job['size']):
                require_audio(part);continue
            tail=None;context_names=[];prefix=motion_prefix(job,seg)
            if prefix:
                source=app.adopted_part(job,job['segments'][i-1])
                context_names,receipt=prepare_motion_tail(source,work/'motion_context',Path(cfg['comfy_input_dir']),f'banana_motion_{job["id"]}_{i:02d}')
                motion_files.extend(Path(cfg['comfy_input_dir'])/name for name in context_names)
                previous=seg.get('motion_context')
                if previous and previous['source_sha256']!=receipt['source_sha256'] and seg.get('prompt_id'):
                    raise ValueError('前段版本已改變，不能沿用舊動作上下文佇列；請建立補拍候選。')
                seg['motion_context']=receipt
            if i and job['request']['mode']=='chain':
                tail=work/f'{i:02d}_opening.png';app.last_frame(app.adopted_part(job,job['segments'][i-1]),tail)
            from banana_mv.takes import existing_file
            prompt_file=existing_file(job,i,seg.get('selected_take','original'),'prompt.txt')
            if prompt_file.exists() and not seg.get('refresh_prompt'):prompt=prompt_file.read_text(encoding='utf-8')
            else:
                prompt_file=work/f'{i:02d}_prompt_v1.txt'
                job['status']='running';seg['status']='rewriting';app.write_state(job)
                prompt=write_prompt(cfg,job,seg,originals,tail);prompt_file.write_text(prompt,encoding='utf-8')
                seg.pop('prompt_id',None);seg.pop('refresh_prompt',None)
            seg.update(prompt=prompt,status='generating');job['status']='running';app.write_state(job)
            first=None
            if tail:
                first=f'banana_film_{job["id"]}_{i}.png';shutil.copyfile(tail,Path(cfg['comfy_input_dir'])/first)
            graph=app.build_workflow(job['images_comfy'],None,*job['size'],seg['model_frames'],prompt,
                                     (job['seed']+i)%(2**48),first,**app.graph_options(job['request'],seg['seconds'],seg))
            if context_names:add_motion_guide(graph,context_names,seg['frames'])
            graph['16']['inputs']['filename_prefix']=f'BananaFilm/{job["id"]}/{i:02d}_v1'
            atomic_json(work/f'{i:02d}_workflow_v1.json',graph);app.preflight(cfg,graph)
            entry=app.backend.history_entry(cfg,seg['prompt_id']) if seg.get('prompt_id') else None
            if entry is None and job.get('resuming'):seg.pop('prompt_id',None)
            if entry and entry.get('status',{}).get('status_str')=='error':entry=None;seg.pop('prompt_id',None)
            if not entry or not entry.get('status',{}).get('completed'):
                if not seg.get('prompt_id'):seg['prompt_id']=app.backend.queue_prompt(cfg,graph);app.write_state(job)
                entry=app.wait_generation(cfg,seg['prompt_id'],job)
            app.backend.comfy_download(cfg,app.video_info(entry),work/f'{i:02d}_raw_v1.mp4')
            part=work/f'{i:02d}_part_v1.mp4'
            if prefix:trim_native(work/f'{i:02d}_raw_v1.mp4',part,seg['frames'],prefix_frames=prefix)
            else:trim_native(work/f'{i:02d}_raw_v1.mp4',part,seg['frames'])
            if not app.valid_part(part,seg,job['size']):raise ValueError('短片影格或尺寸驗證失敗。')
            seg['status']='done';app.write_state(job)
            if first:(Path(cfg['comfy_input_dir'])/first).unlink(missing_ok=True)
        if job['id'] in app.CANCEL:job['status']='cancelled';app.write_state(job);return
        job['status']='assembling';app.write_state(job);masters.preserve_current(job,work)
        pending=work/'final_pending.mp4'
        app.assemble([app.adopted_part(job,s) for s in job['segments']],None,pending,job['duration'],job['output_size'])
        master=masters.archive(job,work,pending,'original' if not job.get('current_master') else 'resume')
        pending.replace(work/'final.mp4');job['current_master']=master['version']
        try:app.export_finished_video(job,work/'final.mp4')
        except OSError as error:job['export_error']=str(error)
        job.update(status='done',video=f'/api/mv/file?id={job["id"]}')
        job.pop('error',None);job.pop('error_stage',None);job.pop('resuming',None);app.write_state(job)
    except Exception as error:
        job.update(error_stage=job.get('status'),status='error',error=f'{type(error).__name__}: {error}');app.write_state(job)
    finally:
        for path in motion_files:path.unlink(missing_ok=True)
        app.CANCEL.discard(job['id']);app.GPU_LOCK.release()
