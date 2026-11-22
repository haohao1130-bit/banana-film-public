"""Native H3 AV delivery: keep generated speech and ambience, never replace with a song."""
from pathlib import Path
from banana_mv.core import FPS, command, probe


def require_audio(path):
    if not any(s['codec_type']=='audio' for s in probe(path)['streams']):
        raise ValueError('H3 輸出缺少原生音軌，已停止；不以無聲影片冒充影音成片。')


def lead_path(part):
    """末五幀模式：被裁掉的前導聲音另存在毛片旁邊，合成時拿來交叉淡化。"""
    part=Path(part)
    return part.with_name(part.stem+'_lead.wav')


def trim_native(source,dest,frames,*,prefix_frames=0):
    if isinstance(prefix_frames,bool) or prefix_frames not in (0,5):
        raise ValueError('不支援的動作上下文裁除長度。')
    require_audio(source)
    seconds=frames/FPS
    end=prefix_frames+frames
    audio_trim=(f'atrim=start={prefix_frames/FPS:.9f}:end={end/FPS:.9f},asetpts=PTS-STARTPTS,' if prefix_frames else '')
    command(['ffmpeg','-y','-v','error','-i',source,'-map','0:v:0','-map','0:a:0',
             '-vf',f'fps={FPS},trim=start_frame={prefix_frames}:end_frame={end},setpts=PTS-STARTPTS',
             '-af',audio_trim+f'apad,atrim=duration={seconds:.9f},asetpts=PTS-STARTPTS',
             '-t',f'{seconds:.9f}','-r',str(FPS),'-c:v','libx264','-threads','1','-crf','18','-pix_fmt','yuv420p',
             '-c:a','aac','-ar','48000','-ac','2','-b:a','192k','-movflags','+faststart',dest])
    stream=next(s for s in probe(dest)['streams'] if s['codec_type']=='video')
    if int(stream.get('nb_frames',-1))!=frames:raise ValueError('H3 輸出影格不足，停止合成。')
    lead=lead_path(dest)
    if prefix_frames:
        # 畫面的前 5 格是重演上一段結尾，可以丟；聲音不硬切，留給合成時和上一段交叉淡化，
        # 免得 H3 在這 0.2 秒內起的音（字頭、腳步）被吃掉或切出爆音。
        command(['ffmpeg','-y','-v','error','-i',source,'-map','0:a:0',
                 '-af',f'atrim=start=0:end={prefix_frames/FPS:.9f},asetpts=PTS-STARTPTS',
                 '-c:a','pcm_s16le','-ar','48000','-ac','2',lead])
    else:
        lead.unlink(missing_ok=True)


def assemble_native(parts,dest,seconds,output_size=None):
    if not parts:raise ValueError('沒有可合成的短片。')
    for part in parts:require_audio(part)
    listing=Path(dest).with_suffix('.ffconcat')
    listing.write_text('ffconcat version 1.0\n'+''.join(
        "file '"+str(Path(p).resolve()).replace("'","'\\''")+"'\n" for p in parts),encoding='utf-8')
    options=['-c:v','copy']
    if output_size:
        width,height=output_size
        source=next(s for s in probe(parts[0])['streams'] if s['codec_type']=='video')
        if source['width']<width or source['height']<height:raise ValueError('生成尺寸不足。')
        if (source['width'],source['height'])!=(width,height):
            options=['-vf',f'crop={width}:{height}','-c:v','libx264','-threads','1','-crf','18','-pix_fmt','yuv420p']
    leads=[lead_path(p) if i and lead_path(p).is_file() else None for i,p in enumerate(parts)]
    if not any(leads):
        command(['ffmpeg','-y','-v','error','-safe','0','-f','concat','-i',listing,
                 '-map','0:v:0','-map','0:a:0',*options,'-c:a','aac','-ar','48000','-ac','2',
                 '-b:a','192k','-t',f'{seconds:.9f}','-movflags','+faststart',dest])
        return
    # 畫面照 concat 接；聲音逐段接，有前導聲音的段落和上一段結尾交叉淡化，總長不變。
    inputs=['-safe','0','-f','concat','-i',listing]
    graph=[]
    for i,part in enumerate(parts):
        inputs+=['-i',part]
        graph.append(f'[{i+1}:a:0]aresample=48000,aformat=channel_layouts=stereo[a{i}]')
    extra=len(parts)+1
    current='a0'
    for i in range(1,len(parts)):
        if leads[i]:
            inputs+=['-i',leads[i]]
            fade=min(probe_seconds(leads[i]),probe_seconds(parts[i-1])-1/FPS)
            graph.append(f'[{extra}:a:0]aresample=48000,aformat=channel_layouts=stereo[l{i}]')
            graph.append(f'[l{i}][a{i}]concat=n=2:v=0:a=1[b{i}]')
            graph.append(f'[{current}][b{i}]acrossfade=d={fade:.9f}:c1=tri:c2=tri[m{i}]')
            extra+=1
        else:
            graph.append(f'[{current}][a{i}]concat=n=2:v=0:a=1[m{i}]')
        current=f'm{i}'
    command(['ffmpeg','-y','-v','error',*inputs,'-filter_complex',';'.join(graph),
             '-map','0:v:0','-map',f'[{current}]',*options,'-c:a','aac','-ar','48000','-ac','2',
             '-b:a','192k','-t',f'{seconds:.9f}','-movflags','+faststart',dest])


def probe_seconds(path):
    return float(probe(path)['format']['duration'])
