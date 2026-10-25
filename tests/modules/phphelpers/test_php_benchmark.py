"""Reject unoptimized or changed actual-extension preparations before measurements."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
spec=importlib.util.spec_from_file_location('phphelpers_php_benchmark',Path(__file__).with_name('prepare_php_benchmark.py'))
benchmark=importlib.util.module_from_spec(spec);spec.loader.exec_module(benchmark)


class PreparationIdentity(unittest.TestCase):
    def test_native_null_rust_profile_and_selected_optimization(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);extension=root/'swoole.so';extension.write_bytes(b'immutable extension')
            manifest=root/'build-manifest.json'
            def observe(compilation,bits,flags='-g -O2 -std=c++14'):
                manifest.write_text(json.dumps({'rust_compilation':compilation,'inputs':{'fix_halfclose':False}}))
                (root/'export.json').write_text(json.dumps({'files':{p.name:{'sha256':benchmark.sha(p)} for p in [extension,manifest]},
                    'native_compilation_observation':{'make_variables':{'CXXFLAGS':flags}}}))
                return benchmark.optimization_observation({'extension':str(extension),'sha256':benchmark.sha(extension),'rust_feature_bits':bits})
            self.assertIsNone(observe(None,0)['rust_profile'])
            optimized={'artifact':{'profile':{'opt_level':'3','debug_assertions':False}}}
            self.assertEqual(observe(optimized,16777216)['rust_profile']['opt_level'],'3')
            for compilation,flags in [(None,'-O2'),(optimized,'-O3 -O0'),
                    ({'artifact':{'profile':{'opt_level':'3','debug_assertions':True}}},'-O2')]:
                with self.assertRaises(ValueError):observe(compilation,16777216,flags)
            observe(optimized,16777216)
            extension.write_bytes(b'changed extension')
            with self.assertRaisesRegex(ValueError,'Immutable export changed'):
                benchmark.optimization_observation({'extension':str(extension),'sha256':benchmark.sha(extension),'rust_feature_bits':16777216})


if __name__=='__main__':unittest.main()
