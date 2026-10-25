"""Optional discovery failures cannot discard available required dependency flags."""
import importlib.util
from pathlib import Path
import shlex
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
spec=importlib.util.spec_from_file_location('phphelpers_sdk',Path(__file__).with_name('sdk.py'))
sdk=importlib.util.module_from_spec(spec);spec.loader.exec_module(sdk)


class DependencyFlags(unittest.TestCase):
    def test_optional_failure_retains_required_flags_and_error(self):
        packages={'openssl':(0,'-I/ssl/include\n',''),
                  'libpcre2-8':(0,'-I/pcre/include\n',''),
                  'libcurl':(0,'-I"/curl sdk/include"\n','curl warning\n'),
                  'libpq':(1,'','Package libpq was not found\n')}
        def probe(command,**options):
            self.assertEqual(command[:2],['pkg-config','--cflags'])
            code,out,err=packages[command[2]]
            return SimpleNamespace(returncode=code,stdout=out,stderr=err)
        with patch.object(sdk.subprocess,'run',side_effect=probe) as run:
            result=sdk.dependency_flags()
        self.assertEqual(run.call_count,4)
        self.assertEqual(shlex.split(result['stdout']),['-I/ssl/include','-I/pcre/include','-I/curl sdk/include'])
        self.assertEqual(result['returncode'],1)
        self.assertEqual(result['probes']['libpq']['returncode'],1)
        self.assertIn('Package libpq was not found',result['stderr'])
        self.assertEqual(result['probes']['libcurl']['stderr'],'curl warning\n')

    def test_missing_program_keeps_each_os_error(self):
        with patch.object(sdk.subprocess,'run',side_effect=FileNotFoundError('pkg-config missing')):
            result=sdk.dependency_flags()
        self.assertEqual(result['returncode'],1)
        self.assertFalse(result['stdout'].strip())
        self.assertEqual(len(result['probes']),4)
        for row in result['probes'].values():
            self.assertIsNone(row['returncode'])
            self.assertEqual(row['error_type'],'FileNotFoundError')
            self.assertIn('pkg-config missing',row['stderr'])


class FacadeDeclarations(unittest.TestCase):
    def header(self):
        return '#define NATIVE_MACRO(x) ((x)+1)\n'+''.join(
            'class '+name+' {\n  public:\n    int field;\n    int value(int arg) const { return arg; }\n};\n'
            for name in ['String','KeyValue','ArrayIterator','Array','Variable','CharPtr','Callable'])

    def test_body_policy_can_change_without_changing_declarations(self):
        native=self.header();selected=native.replace('return arg;','return rust_policy(arg);')
        result=sdk.facade_surface(native,selected)
        self.assertTrue(result['matched']);self.assertEqual(len(result['classes']),7)
        self.assertEqual(result['macro_definitions'],1)

    def test_same_size_field_or_signature_change_is_rejected(self):
        native=self.header()
        for before,after in [('int field;','unsigned field;'),('value(int arg)','value(unsigned arg)'),('  public:','  private:')]:
            with self.subTest(after=after),self.assertRaisesRegex(ValueError,'declarations changed'):
                sdk.facade_surface(native,native.replace(before,after,1))

    def test_macro_body_change_is_rejected(self):
        native=self.header()
        with self.assertRaisesRegex(ValueError,'macro definitions changed'):
            sdk.facade_surface(native,native.replace('((x)+1)','((x)+2)'))


if __name__=='__main__':unittest.main()
