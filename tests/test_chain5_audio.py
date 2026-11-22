"""末五幀接續：前導 5 格的聲音不硬切，合成時和上一段交叉淡化（真實 FFmpeg）。"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from banana_mv.core import FPS
from banana_mv.film_media import assemble_native, lead_path, probe_seconds, trim_native


def make_clip(path, frames, audio_filter):
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i',
                    f'color=c=gray:s=64x64:r={FPS}:d={frames / FPS}', '-f', 'lavfi', '-i',
                    f'anullsrc=r=48000:cl=stereo:d={frames / FPS}', '-filter_complex', audio_filter,
                    '-map', '0:v', '-map', '[a]', '-frames:v', str(frames), '-c:v', 'libx264',
                    '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(path)], check=True)


def window_volume(path, start, end):
    out = subprocess.run(['ffmpeg', '-v', 'info', '-ss', str(start), '-t', str(end - start), '-i', str(path),
                          '-map', '0:a', '-af', 'volumedetect', '-f', 'null', '-'],
                         capture_output=True, text=True).stderr
    return float(out.split('max_volume:')[1].split('dB')[0])


@unittest.skipUnless(shutil.which('ffmpeg'), 'needs ffmpeg')
class Chain5AudioTests(unittest.TestCase):
    def test_lead_in_sound_survives_and_length_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            raw_a, raw_b = tmp / 'a_raw.mp4', tmp / 'b_raw.mp4'
            part_a, part_b = tmp / '00_part.mp4', tmp / '01_part.mp4'
            make_clip(raw_a, 48, '[1:a]anull[a]')                          # 上一段全靜音
            beep = 'sine=f=880:d=0.2:r=48000,adelay=100|100,apad,aformat=channel_layouts=stereo'
            make_clip(raw_b, 53, f'{beep}[s];[1:a][s]amix=inputs=2:normalize=0[a]')  # 0.1 秒開始嗶
            trim_native(raw_a, part_a, 48)
            trim_native(raw_b, part_b, 48, prefix_frames=5)
            self.assertFalse(lead_path(part_a).exists())
            self.assertAlmostEqual(probe_seconds(lead_path(part_b)), 5 / FPS, places=2)
            final = tmp / 'final.mp4'
            assemble_native([part_a, part_b], final, 96 / FPS)
            self.assertAlmostEqual(probe_seconds(final), 4.0, delta=0.05)
            # 交接點前 0.2 秒：舊做法這裡完全無聲（嗶聲的開頭被切掉），新做法聽得到淡入的嗶聲。
            self.assertGreater(window_volume(final, 1.88, 2.0), -40)

    def test_no_prefix_removes_stale_lead(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            raw, part = tmp / 'raw.mp4', tmp / 'part.mp4'
            make_clip(raw, 53, '[1:a]anull[a]')
            trim_native(raw, part, 48, prefix_frames=5)
            self.assertTrue(lead_path(part).exists())
            trim_native(raw, part, 48)
            self.assertFalse(lead_path(part).exists())


if __name__ == '__main__':
    unittest.main()
