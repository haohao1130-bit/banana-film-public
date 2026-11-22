"""Project-scoped dish auditions on the existing Film renderer."""
import json
import math
import threading

from banana_mv import film, server as app
from banana_mv.core import FPS
from banana_mv.film_continuity import render_frames


def new_attempt(prompt, seconds):
    return {'menu': prompt, 'seconds': seconds, 'clips': []}


def latest(job):
    return job['kitchen']['dishes'][-1]['attempts'][-1]


def adopted(job):
    return [index for dish in job['kitchen']['dishes'] if 'selected' in dish
            for index in dish['attempts'][dish['selected']]['clips']]


def prepare(job, cfg, originals):
    """Append an audition without rewriting existing clip indices or files."""
    kitchen = job['kitchen']
    attempt = latest(job)
    if kitchen.get('serving') or attempt['clips']:
        return
    if not job['segments']:
        shared = job['request'].get('kitchen_shared_setup', '').strip()
        if shared:
            shared = film.map_story(job['request'], shared, len(originals))
            if not all(f'<Picture {index}>' in shared for index in range(1, len(originals) + 1)):
                # Preserve explicit settings and let the planner fill omitted image bindings.
                shared = None
        plan = film.plan_film(cfg, job, originals, shared_setup=shared or None)
        job.update(segments=plan['segments'], shared_setup=plan['shared_setup'], duration=plan['duration'])
        if not job['request'].get('project_name'):
            job['title'] = plan['title']
        attempt['clips'] = list(range(len(job['segments'])))
        return

    from banana_mv.film_act import split_clip_commissions
    request = dict(job['request'], prompt=attempt['menu'], target_seconds=attempt['seconds'],
                   max_seconds=attempt['seconds'] + 1.5, timeline_tolerance=1.5,
                   target_is_exact=True, duration_source='selector', authored_clip_commissions=False,
                   authored_act_commissions=False)
    explicit = split_clip_commissions(attempt['menu'], request['segment_seconds'])
    if explicit:
        request['authored_clip_commissions'] = True
        _, scenes = explicit
        plan = film.validate_plan(json.dumps({
            'title': job['title'], 'shared_setup': job['shared_setup'],
            'segments': [{'seconds': seconds, 'mode': mode, 'brief': brief}
                         for seconds, mode, brief in scenes],
        }, ensure_ascii=False), request, len(originals))
        film.validate_planned_duration(plan, request)
    else:
        work = app.job_dir(job['id']) / 'kitchen' / str(len(job['segments']))
        work.mkdir(parents=True, exist_ok=True)
        plan = film.plan_film(cfg, dict(job, request=request), originals,
                              work=work, shared_setup=job['shared_setup'])
    previous = adopted(job)
    cursor = sum(job['segments'][index]['frames'] for index in previous)
    first_index = len(job['segments'])
    for offset, segment in enumerate(plan['segments']):
        index = first_index + offset
        segment.update(index=index, start_frame=cursor, start=cursor / FPS,
                       fixed_reference_settings=job['shared_setup'])
        segment['director_plan']['index'] = index
        if request['mode'] == 'chain5' and (offset or previous):
            segment['model_frames'] = render_frames(segment['frames'])
        if offset == 0:
            segment['kitchen_previous'] = previous[-1] if previous else None
        segment['authored_clip_commission'] = request['authored_clip_commissions']
        cursor += segment['frames']
    attempt['clips'] = list(range(first_index, first_index + len(plan['segments'])))
    job['segments'].extend(plan['segments'])
    job['duration'] = cursor / FPS


def update(body, action):
    if not app.GPU_LOCK.acquire(blocking=False):
        raise ValueError('鐵板正在使用中，請等這次生成完成。')
    started = False
    try:
        job = app.read_state(body['id'])
        kitchen = job.get('kitchen')
        if not kitchen or job['status'] != 'kitchen_ready':
            raise ValueError('請從待試菜或待上菜的鐵板燒專案操作。')
        dishes = kitchen['dishes']
        current = dishes[-1]
        if action == 'adopt':
            selection = body.get('attempt')
            if ('selected' in current or type(selection) is not int
                    or not 0 <= selection < len(current['attempts'])):
                raise ValueError('請選擇目前這道菜的毛片版本。')
            indices = current['attempts'][selection]['clips']
            from banana_mv.takes import take_source
            for index in indices:
                take_source(job, index)
            if not indices:
                raise ValueError('這版毛片尚未完成。')
            current['selected'] = selection
            job['duration'] = sum(job['segments'][i]['frames'] for i in adopted(job)) / FPS
            app.write_state(job)
            return job

        serving = action == 'serve'
        if serving:
            if any('selected' not in dish for dish in dishes):
                raise ValueError('請先採用每道菜的毛片版本。')
            if type(body.get('upscale', False)) is not bool:
                raise ValueError('升頻設定必須為勾選值。')
            kitchen['serving'] = True
            job['request']['upscale_1080p'] = body.get('upscale', False)
        else:
            if (action == 'repeat') == ('selected' in current):
                raise ValueError('請先採用這道菜，或重炒尚未採用的菜。')
            text = body.get('menu')
            seconds = body.get('seconds')
            if not isinstance(text, str) or not 1 <= len(text.strip()) <= 30000:
                raise ValueError('請輸入菜單，最多 30000 字。')
            if type(seconds) not in (float, int) or not math.isfinite(seconds) or not 6 <= seconds <= 300:
                raise ValueError('每道菜長度需介於 6–300 秒。')
            attempt = new_attempt(text.strip(), seconds)
            if action == 'repeat':
                current['attempts'].append(attempt)
            else:
                dishes.append({'attempts': [attempt]})

        cfg = app.backend.project_config(job['request'])
        originals = [app.backend.safe_child(app.job_dir(job['id']), rel) for rel in job['sources']['images']]
        if not serving:
            queue = app.backend.comfy(cfg, '/queue')
            if queue.get('queue_running') or queue.get('queue_pending'):
                raise ValueError('ComfyUI 還有工作，請稍後再開拍。')
            originals, _, _ = film.inputs(job, cfg)
        job.update(status='assembling' if serving else 'planning_story')
        job.pop('error', None)
        job.pop('error_stage', None)
        app.write_state(job)
        threading.Thread(target=film.worker, args=(job, cfg, originals), daemon=True).start()
        started = True
        return job
    finally:
        if not started:
            app.GPU_LOCK.release()
