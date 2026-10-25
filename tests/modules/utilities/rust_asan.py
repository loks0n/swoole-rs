"""Inspect exact utility Rust objects, independently of bundled bitcode readers."""
from pathlib import Path
import re
import subprocess
import tempfile


def inspect(archive, additional_exports=()):
    archive = Path(archive).resolve(strict=True)
    report = dict(archive=str(archive), members=[])
    names = subprocess.check_output(['ar', 't', str(archive)], text=True).splitlines()
    names = [n for n in names if n.startswith('swoole_rs_utilities-') and n.endswith('.rcgu.o')]
    if not names or len(names) != len(set(names)):
        raise ValueError('Missing or duplicate utility Rust code objects')
    header = Path(__file__).resolve().parents[3] / 'native/utilities/swoole_rs_utilities.h'
    expected = set(re.findall(r'\b(swr_v1_utils_log_(?:state|path)_\w+)\(', header.read_text()))
    if not expected:
        raise ValueError('Missing owned-state ABI declarations')
    instrumented = set()
    extra_instrumented = set()
    with tempfile.TemporaryDirectory(prefix='utility-asan-objects-') as temporary:
        for index, name in enumerate(names):
            data = subprocess.check_output(['ar', 'p', str(archive), name])
            obj = Path(temporary) / (str(index) + '.o')
            obj.write_bytes(data)
            undefined = subprocess.check_output(['nm', '-u', str(obj)], stderr=subprocess.STDOUT, text=True)
            defined = subprocess.check_output(['nm', '-g', str(obj)], stderr=subprocess.STDOUT, text=True)
            imports = sorted(set(re.findall(r'(?<![A-Za-z0-9])_?(__asan_(?:report|load|store)\w*)', undefined)))
            state = sorted(set(re.findall(r'^[0-9a-fA-F]+\s+T\s+_?(swr_v1_utils_log_(?:state|path)_\w+)\s*$', defined, re.M)))
            if imports:
                instrumented.update(state)
                extra_instrumented.update(re.findall(r'^[0-9a-fA-F]+\s+T\s+_?(swr_v2_utils_\w+)\s*$', defined, re.M))
            report['members'].append(dict(name=name, bytes=len(data), asan_imports=imports, state_symbols=state,
                                          undefined_symbols=undefined, global_symbols=defined))
    if not expected <= instrumented:
        raise ValueError('Owned Logger Rust definitions lack AddressSanitizer object imports: ' + str(sorted(expected - instrumented)))
    if not set(additional_exports) <= extra_instrumented:
        raise ValueError('Additional utility definitions lack ASan imports: ' + str(sorted(set(additional_exports) - extra_instrumented)))
    report['additional_definitions_in_instrumented_objects'] = sorted(extra_instrumented)
    report['owned_state_definitions_in_instrumented_objects'] = sorted(instrumented)
    report['owned_state_instrumentation_observed'] = True
    return report
