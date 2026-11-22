"""蕉彌鐵板燒共同設定組合：存、同名更新、素材遺失提示、刪除。"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from banana_mv import services, teppan_presets


class PresetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        library = root / 'library'
        library.mkdir()
        (library / 'xiaowu.png').write_bytes(b'png')
        (library / 'library.json').write_text(json.dumps([
            {'id': 'img1', 'file': 'xiaowu.png', 'kind': 'image'},
            {'id': 'song', 'file': 'song.mp3', 'kind': 'audio'}]), encoding='utf-8')
        self.patches = [patch.object(services, 'DATA', root), patch.object(services, 'LIBRARY', library)]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in self.patches:
            item.stop()
        self.tmp.cleanup()

    def slots(self, *ids):
        return list(ids) + [None] * (8 - len(ids))

    def test_save_update_and_delete(self):
        rows = teppan_presets.save_preset({'name': '異世界食堂', 'shared': '@圖片1=小巫', 'slots': self.slots('img1')})
        self.assertEqual([(r['name'], r['slots'][0], r['missing']) for r in rows], [('異世界食堂', 'img1', [])])
        rows = teppan_presets.save_preset({'name': '異世界食堂', 'shared': '改過', 'slots': self.slots('img1')})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['shared'], '改過')
        rows = teppan_presets.delete_preset({'id': rows[0]['id']})
        self.assertEqual(rows, [])

    def test_rejects_unknown_or_non_image_assets_and_empty(self):
        for slots in (self.slots('nope'), self.slots('song')):
            with self.assertRaisesRegex(ValueError, '找不到這張參考圖'):
                teppan_presets.save_preset({'name': 'x', 'shared': 'y', 'slots': slots})
        with self.assertRaisesRegex(ValueError, '空的'):
            teppan_presets.save_preset({'name': 'x', 'shared': ' ', 'slots': self.slots()})
        with self.assertRaisesRegex(ValueError, '名稱'):
            teppan_presets.save_preset({'name': '', 'shared': 'y', 'slots': self.slots()})

    def test_missing_library_image_is_reported(self):
        teppan_presets.save_preset({'name': '食堂', 'shared': 'y', 'slots': self.slots('img1')})
        (services.LIBRARY / 'library.json').write_text('[]', encoding='utf-8')
        self.assertEqual(teppan_presets.list_presets()[0]['missing'], [1])

    def test_asset_path_stays_inside_library(self):
        self.assertEqual(teppan_presets.image_asset('img1')[1].name, 'xiaowu.png')


if __name__ == '__main__':
    unittest.main()
