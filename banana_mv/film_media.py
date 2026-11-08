"""Native H3 AV delivery: keep generated speech and ambience, never replace with a song."""
from pathlib import Path
from banana_mv.core import FPS, command, probe


def require_audio(path):
    if not any(s['codec_type']=='audio' for s in probe(path)['streams']):
        raise ValueError('H3 輸出缺少原生音軌，已停止；不以無聲影片冒充影音成片。')


def trim_native(source,dest,frames):
    require_audio(source)
    seconds=frames/FPS
    command(['ffmpeg','-y','-v','error','-i',source,'-map','0:v:0','-map','0:a:0',
             '-vf',f'fps={FPS},trim=end_frame={frames},setpts=PTS-STARTPTS',
             '-af',f'apad,atrim=duration={seconds:.9f},asetpts=PTS-STARTPTS',
             '-t',f'{seconds:.9f}','-c:v','libx264','-threads','1','-crf','18','-pix_fmt','yuv420p',
             '-c:a','aac','-ar','48000','-ac','2','-b:a','192k','-movflags','+faststart',dest])
    stream=next(s for s in probe(dest)['streams'] if s['codec_type']=='video')
    if int(stream.get('nb_frames',-1))!=frames:raise ValueError('H3 輸出影格不足，停止合成。')


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
    command(['ffmpeg','-y','-v','error','-safe','0','-f','concat','-i',listing,
             '-map','0:v:0','-map','0:a:0',*options,'-c:a','aac','-ar','48000','-ac','2',
             '-b:a','192k','-t',f'{seconds:.9f}','-movflags','+faststart',dest])


