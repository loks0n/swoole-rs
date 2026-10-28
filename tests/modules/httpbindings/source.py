"""Extract a named actual function definition, skipping forward declarations."""
from pathlib import Path
import re

def definition(source, signature):
    cursor = 0
    while True:
        start = source.find(signature, cursor)
        if start < 0:
            raise ValueError('Missing definition: ' + signature)
        opening = source.find('{', start)
        if opening < 0:
            raise ValueError('Missing body: ' + signature)
        cursor = start + len(signature)
        if ';' in source[start:opening]:
            continue
        depth = 0
        # The selected native bodies contain balanced braces in their literals.
        for end in range(opening, len(source)):
            if source[end] == '{':
                depth += 1
            elif source[end] == '}':
                depth -= 1
                if depth == 0:
                    return source[start:end + 1]
        raise ValueError('Unterminated definition: ' + signature)


def rust_declarations(text, flags):
    """#include lines for the Rust ABI headers (from hybrid_tree flags) that declare the
    swr_* functions a hybrid-side fragment calls."""
    headers = [path for flag in flags if flag.startswith('-I') for path in sorted(Path(flag[2:]).glob('swoole_rs*.h'))]
    names = set(re.findall(r'\bswr_v\d+_\w+', text))
    return ''.join('#include "' + header.name + '"\n' for header in headers
                   if any(re.search(r'\b' + name + r'\s*\(', header.read_text()) for name in names))
