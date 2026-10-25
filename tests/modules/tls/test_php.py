#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('tls_php',Path(__file__).with_name('php.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class ExportIdentity(unittest.TestCase):
    def test_legacy_and_files_preserve_real_reference_attestation_scope(self):
        h='a'*64;build={'migrated_feature_bits':8388607}
        legacy={'selected_source_commit':'b'*40,'feature_bits':8388607,'manifest_sha256':h,
            'extension':{'sha256':h},'archive':{'sha256':h},'reference':{'sha256':h}}
        newer={'source_ref':'b'*40,'reference_build_attestation':False,
            'engines':[{'name':'hybrid','rust_feature_bits':8388607}],
            'files':{name:{'sha256':h}for name in ['swoole.so','reference.so','libswoole_rs_ffi.a','build-manifest.json']}}
        a=module.artifact_identity(legacy,build);b=module.artifact_identity(newer,build)
        self.assertIsNone(a['reference_build_attestation']);self.assertIs(b['reference_build_attestation'],False)
        for key in ['selected_source_commit','feature_bits','manifest_sha256','extension_sha256','archive_sha256','reference_sha256']:
            self.assertEqual(a[key],b[key])
        self.assertNotIn('manifest_sha256',newer) # Never rewrite the actual producer schema.
        newer['engines'][0]['rust_feature_bits']=0
        with self.assertRaises(ValueError):module.artifact_identity(newer,build)
    def test_missing_or_malformed_identity_stays_failure(self):
        build={'migrated_feature_bits':1}
        for x in [{},{'files':{},'source_ref':'bad'}]:
            with self.assertRaises((KeyError,ValueError)):module.artifact_identity(x,build)

if __name__=='__main__':unittest.main()
