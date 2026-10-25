"""Optional Rust ASan import check and sanitizer stderr classification."""
from pathlib import Path
import re
import subprocess

def identify(path, rust_asan=False):
    path=Path(path).resolve(strict=True)
    result={'path':str(path),'rust_instruction_asan_requested':rust_asan}
    if rust_asan:
        probe=subprocess.run(['nm','-u',str(path)],text=True,capture_output=True,check=True)
        imports=sorted(set(re.findall(r'\b__asan_(?:report_)?(?:load|store)\w*',probe.stdout)))
        if not any('load' in x for x in imports) or not any('store' in x for x in imports):
            raise ValueError('Selected Rust archive lacks load/store ASan instrumentation imports')
        result.update(rust_instruction_asan_imports=imports)
    return result

def sanitizer_outcome(stderr):
    if re.search(r'(?:ERROR|SUMMARY): (?:AddressSanitizer|LeakSanitizer)|runtime error:|AddressSanitizer:DEADLYSIGNAL',stderr):
        return 'failed'
    if re.search(r'WARNING: (?:ASan|AddressSanitizer|LeakSanitizer)',stderr):
        return 'warned'
    return 'passed'
