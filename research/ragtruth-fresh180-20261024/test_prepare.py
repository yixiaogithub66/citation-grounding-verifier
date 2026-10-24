import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('fresh_prepare',Path(__file__).with_name('prepare.py'))
prepare=importlib.util.module_from_spec(spec);spec.loader.exec_module(prepare)

class PreparationBoundaryTests(unittest.TestCase):
    def test_context_hash_preserves_exact_content_and_order(self):
        self.assertNotEqual(prepare.context_sha(['A','B']),prepare.context_sha(['B','A']))
        self.assertNotEqual(prepare.context_sha(['A']),prepare.context_sha([' A']))
        self.assertEqual(prepare.context_sha(['A']),prepare.context_sha(['A']))

    def test_modified_frozen_code_or_sampling_policy_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'source';source.mkdir()
            code=source/'module.py';code.write_text('x=1\n')
            sample=root/'sampling.json';sample.write_text('{}')
            audit=root/'exposure.json';audit.write_text('{}')
            pre=root/'preselection.json'
            value={'source_root':str(source),'code_files_sha256':{'module.py':prepare.sha(code)},
                   'sampling_preselection_path':str(sample),'sampling_preselection_sha256':prepare.sha(sample),
                   'exposure_audit_path':str(audit),'exposure_audit_sha256':prepare.sha(audit)}
            prepare.write(pre,value);self.assertEqual(prepare.check(pre),value)
            code.write_text('x=2\n')
            with self.assertRaisesRegex(ValueError,'snapshot'):prepare.check(pre)
            code.write_text('x=1\n');sample.write_text('{"changed":true}')
            with self.assertRaisesRegex(ValueError,'Sampling'):prepare.check(pre)

    def test_manifest_self_hash_and_nonoverwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'preselection.json';prepare.write(path,{})
            with self.assertRaises(FileExistsError):prepare.write(path,{})
            path.write_text('{"changed":true}')
            with self.assertRaisesRegex(ValueError,'self hash'):prepare.check(path)

if __name__=='__main__':unittest.main()
