"""Native H3 AV delivery: keep generated speech and ambience, never replace with a song."""
from pathlib import Path
from banana_mv.core import FPS, command, probe


def require_audio(path):
    if not any(s['codec_type']=='audio' for s in probe(path)['streams']):
        raise ValueError('H3 輸出缺少原生音軌，已停止；不以無聲影片冒充影音成片。')


SEAM_FADE=0.03
TAIL_SPILL=0.5      # 上一段被裁掉的尾音最多疊到下一段開頭 0.5 秒
TAIL_FADE=0.25      # 疊過去的尾音在最後 0.25 秒淡出


def lead_path(part):
    """末五幀模式：被裁掉的前導聲音另存在毛片旁邊，合成時拿最後 30 毫秒做接縫淡化。"""
    part=Path(part)
    return part.with_name(part.stem+'_lead.wav')


def tail_path(part):
    """H3 算圖比交付長時，結尾被裁掉的聲音另存在毛片旁邊，合成時疊到下一段開頭。"""
    part=Path(part)
    return part.with_name(part.stem+'_tail.wav')


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
    tail=tail_path(dest)
    overrun=probe_seconds(source)-end/FPS
    if overrun>=3/FPS:
        # 末五幀 10 秒要算 260 格，交付只取中間 240 格：H3 排在最後的腳步聲、最後一個字
        # 會落在被裁掉的 0.6 秒裡（實測 cf9f52c7f21f）。另存起來，合成時延續到下一段。
        command(['ffmpeg','-y','-v','error','-i',source,'-map','0:a:0',
                 '-af',f'atrim=start={end/FPS:.9f}:duration={TAIL_SPILL:.9f},asetpts=PTS-STARTPTS',
                 '-c:a','pcm_s16le','-ar','48000','-ac','2',tail])
    else:
        tail.unlink(missing_ok=True)


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
    tails=[tail_path(p) if i+1<len(parts) and tail_path(p).is_file() else None for i,p in enumerate(parts)]
    if not any(leads) and not any(tails):
        command(['ffmpeg','-y','-v','error','-safe','0','-f','concat','-i',listing,
                 '-map','0:v:0','-map','0:a:0',*options,'-c:a','aac','-ar','48000','-ac','2',
                 '-b:a','192k','-t',f'{seconds:.9f}','-movflags','+faststart',dest])
        return
    # 畫面照 concat 接；聲音逐段接：上一段被裁掉的尾音疊到這段開頭並淡出，
    # 有前導聲音的段落和上一段結尾做 30 毫秒接縫淡化，總長不變。
    inputs=['-safe','0','-f','concat','-i',listing]
    graph=[]
    for i,part in enumerate(parts):
        inputs+=['-i',part]
        graph.append(f'[{i+1}:a:0]aresample=48000,aformat=channel_layouts=stereo[a{i}]')
    extra=len(parts)+1
    labels=[f'a{i}' for i in range(len(parts))]
    for i in range(1,len(parts)):
        if not tails[i-1]:
            continue
        inputs+=['-i',tails[i-1]]
        spill=probe_seconds(tails[i-1])
        fade=min(TAIL_FADE,spill)
        graph.append(f'[{extra}:a:0]aresample=48000,aformat=channel_layouts=stereo,'
                     f'afade=t=out:st={spill-fade:.9f}:d={fade:.9f}[t{i}]')
        graph.append(f'[a{i}][t{i}]amix=inputs=2:duration=first:normalize=0[s{i}]')
        labels[i]=f's{i}'
        extra+=1
    current=labels[0]
    for i in range(1,len(parts)):
        if leads[i]:
            inputs+=['-i',leads[i]]
            # 只用前導最後 30 毫秒和上一段收尾做極短淡化，避免爆音；
            # 不再拿整段 0.208 秒淡化，否則上一段最後一個字會被淡掉（實測 cf9f52c7f21f）。
            lead_seconds=probe_seconds(leads[i])
            fade=max(min(SEAM_FADE,lead_seconds,probe_seconds(parts[i-1])-1/FPS),0.001)
            graph.append(f'[{extra}:a:0]atrim=start={lead_seconds-fade:.9f},asetpts=PTS-STARTPTS,'
                         f'aresample=48000,aformat=channel_layouts=stereo[l{i}]')
            graph.append(f'[l{i}][{labels[i]}]concat=n=2:v=0:a=1[b{i}]')
            graph.append(f'[{current}][b{i}]acrossfade=d={fade:.9f}:c1=tri:c2=tri[m{i}]')
            extra+=1
        else:
            graph.append(f'[{current}][{labels[i]}]concat=n=2:v=0:a=1[m{i}]')
        current=f'm{i}'
    command(['ffmpeg','-y','-v','error',*inputs,'-filter_complex',';'.join(graph),
             '-map','0:v:0','-map',f'[{current}]',*options,'-c:a','aac','-ar','48000','-ac','2',
             '-b:a','192k','-t',f'{seconds:.9f}','-movflags','+faststart',dest])


def probe_seconds(path):
    return float(probe(path)['format']['duration'])
