"""Release boundary: anonymous notebook and reproducible clean source inventory."""
import ast
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PublicFilmTests(unittest.TestCase):
    def test_notebook_is_anonymous_clean_and_targets_public_film(self):
        nb = json.loads((ROOT/'Banana_Film_Studio.ipynb').read_text())
        text = '\n'.join(''.join(c['source']) for c in nb['cells'])
        self.assertIn('https://github.com/haohao1130-bit/banana-film-public.git', text)
        self.assertNotIn('userdata.get(\'GITHUB' + '_TOKEN\')', text)
        self.assertNotIn('private_clone', text)
        for cell in nb['cells']:
            if cell['cell_type'] == 'code':
                self.assertEqual(cell['outputs'], [])
                self.assertIsNone(cell['execution_count'])
                ast.parse(''.join(cell['source']))

    def test_release_inventory_matches_and_contains_no_private_contact_or_keys(self):
        manifest = json.loads((ROOT/'PUBLIC_MANIFEST.json').read_text())
        self.assertEqual(manifest['repository'], 'haohao1130-bit/banana-film-public')
        forbidden = re.compile(r'[\w.+-]+@(?:gmail|yahoo|hotmail|outlook)\.[a-z]+|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----')
        for entry in manifest['files']:
            file = ROOT/entry['path']
            self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(), entry['sha256'], entry['path'])
            self.assertIsNone(forbidden.search(file.read_text()), entry['path'])


if __name__ == '__main__':
    unittest.main()
