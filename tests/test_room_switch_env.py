import base64
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from banana_mv import room_switch


class RoomSwitchEnvironmentTests(unittest.TestCase):
    def test_clean_environment_drops_this_rooms_python_setup(self):
        env = room_switch.clean_environment({
            'PATH': r'F:\film-venv\Scripts;C:\Windows', 'VIRTUAL_ENV': r'F:\film-venv', 'PYTHONPATH': 'x',
            'PYTHONHOME': 'y', 'BANANA_DATA': 'z', 'CONDA_PREFIX': 'c', 'PIP_INDEX_URL': 'p',
            'CUDA_VISIBLE_DEVICES': '', 'SystemRoot': r'C:\Windows', 'LOCALAPPDATA': r'C:\Users\a\AppData\Local'})
        self.assertEqual(sorted(env), ['LOCALAPPDATA', 'PATH', 'SystemRoot'])

    def test_switch_resets_path_and_passes_clean_environment(self):
        # 實測：從鐵板燒切到 MV，音樂分析載入 torch_python.dll 被擋（WinError 4551）；手動開 MV 正常。
        handler = SimpleNamespace(headers={'Origin': 'http://127.0.0.1:8193', 'Host': '127.0.0.1:8193',
                                           'X-Banana-Control': '5070-room-switch'},
                                  send_json=Mock(), server=SimpleNamespace(shutdown=Mock()))
        backend = SimpleNamespace(PORT=8193, comfy=Mock(return_value={'queue_running': [], 'queue_pending': []}),
                                  load_config=Mock(return_value={}), DATA=Path('/tmp'))
        lock = MagicMock(); lock.acquire.return_value = True
        with patch.object(room_switch, 'launcher', return_value=Path('/tmp/Launch.ps1')), \
             patch.dict(room_switch.os.environ, {'VIRTUAL_ENV': r'F:\film-venv', 'PATH': r'F:\film-venv\Scripts'}), \
             patch.object(room_switch.subprocess, 'Popen', create=True) as spawn, \
             patch.object(room_switch.subprocess, 'CREATE_NEW_CONSOLE', 16, create=True):
            room_switch.switch(handler, 'mv', backend, lock)
        args, kwargs = spawn.call_args
        command = base64.b64decode(args[0][args[0].index('-EncodedCommand') + 1]).decode('utf-16-le')
        self.assertIn("GetEnvironmentVariable('Path','Machine')", command)
        self.assertLess(command.index("GetEnvironmentVariable('Path','Machine')"), command.index("& '"))
        self.assertNotIn('VIRTUAL_ENV', kwargs['env'])


if __name__ == '__main__':
    unittest.main()
