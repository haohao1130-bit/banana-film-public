"""Exercise owned storage and local rewriter without upstream files or a GPU."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from banana_mv import services


class ServicesTests(unittest.TestCase):
    def test_film_upload_identifies_images_without_extension_and_rejects_audio(self):
        import io
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cfg={'comfy_input_dir':str(root/'input')}
            body=io.BytesIO();Image.new('RGB',(12,8)).save(body,format='JPEG')
            with patch.object(services,'LIBRARY',root/'library'):
                for name in ('jpg','角色圖','角色圖.bin','角色圖.PNG'):
                    row=services.add_asset(cfg,name,body.getvalue(),image_only=True)
                    self.assertEqual(row['kind'],'image')
                    self.assertTrue(row['file'].endswith('.jpg'))
                    self.assertEqual(row['name'],name)
                before=services.library_index()
                with self.assertRaisesRegex(ValueError,'圖片'):
                    services.add_asset(cfg,'sound.wav',b'RIFF-not-an-image',image_only=True)
                self.assertEqual(services.library_index(),before)

    def test_existing_library_restore_and_path_safety(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);lib=root/'library';lib.mkdir();inp=root/'input'
            with patch.object(services,'DATA',root),patch.object(services,'LIBRARY',lib):
                (root/'config.json').write_text(json.dumps({'comfy_input_dir':str(inp),
                    'rewriter':{'openai':{'api_key':'do-not-load'},'temperature':0.5},
                    'guides':{'ref':'old/frontend/guide.md'}}))
                (lib/'old.png').write_bytes(b'preserved-original')
                (lib/'library.json').write_text(json.dumps([{'id':'legacy','file':'old.png','comfy_name':'h3fe_old.png'}]))
                cfg=services.load_config()
                self.assertNotIn('openai',cfg['rewriter'])
                self.assertEqual(cfg['rewriter']['temperature'],0.5)
                self.assertNotIn('old/frontend',cfg['guides']['ref'])
                self.assertEqual(services.restore_inputs(cfg),1)
                self.assertEqual((inp/'h3fe_old.png').read_bytes(),b'preserved-original')
                self.assertEqual(services.asset('legacy')['file'],'old.png')
                with self.assertRaises(ValueError):services.safe_child(lib,'../config.json')
                with self.assertRaises(ValueError):services.add_asset(cfg,'bad.png',b'not an image')
                self.assertEqual(len(services.library_index()),1)

    def test_rewriter_contract_cleanup_and_unload(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg=services.load_config();cfg['comfy_input_dir']=tmp
            pics=[Image.new('RGB',(64,64),c) for c in ('red','blue')]
            parts=[('text','<Picture 1>'),('image',pics[0]),('text','<Picture 2>'),('image',pics[1])]
            captured=[];uploaded=[]
            def queue(config,graph):captured.append(graph);return 'prompt'
            def upload(config,name,data,mime):
                self.assertEqual(mime,'image/jpeg')
                self.assertTrue(data.startswith(bytes.fromhex('ffd8')))
                uploaded.append(name)
                return name
            with patch.object(services,'upload_comfy_image',side_effect=upload),\
                 patch.object(services,'queue_prompt',side_effect=queue),\
                 patch.object(services,'wait_prompt',return_value={'outputs':{'result':{'text':['hello']}}}),\
                 patch.object(services,'comfy',return_value={}) as api:
                self.assertEqual(services.rewrite_local(cfg,'guide',parts,'test'),'hello')
                api.assert_called_once_with(cfg,'/free',{'unload_models':True,'free_memory':True})
            self.assertEqual(len(uploaded),2)
            graph=captured[0]
            self.assertEqual(graph['generate']['inputs']['image'],['batch_1',0])
            self.assertEqual(graph['batch_1']['inputs']['image1'],['picture_0',0])
            self.assertEqual(graph['generate']['inputs']['prompt'].count('<|image_pad|>'),2)
            self.assertEqual(graph['generate']['inputs']['max_length'],8192)
            self.assertEqual(list(Path(tmp).glob('*.jpg')),[])
            with patch.object(services,'upload_comfy_image',side_effect=upload),\
                 patch.object(services,'queue_prompt',side_effect=RuntimeError('rejected')):
                with self.assertRaisesRegex(RuntimeError,'rejected'):
                    services.rewrite_local(cfg,'guide',parts,'failed')
            self.assertEqual(list(Path(tmp).glob('*.jpg')),[])

