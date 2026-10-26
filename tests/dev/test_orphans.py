"""Every file under tests/modules is referenced by some other tracked file: by name,
by its stem as a quoted string or an import. A file beside a same-stem .py (the
C++ a gate compiles with Path(__file__).with_suffix) is referenced when it is.
Markdown does not count, so a file only a README mentions is an orphan. orphans.txt lists the ones not yet wired into
a gate or deleted (#47); it may only shrink."""
from collections import Counter
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
ALLOWED = Path(__file__).with_name('orphans.txt')
NAMES = re.compile(r'[\w.-]+')
QUOTED = re.compile(r'''['"]([\w.-]+)['"]|(?:import|from)\s+(?:[\w]+\.)*(\w+)''')


def tokens(text):
    return set(NAMES.findall(text)), {a or b for a, b in QUOTED.findall(text)}


def orphans():
    files = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files'], text=True).splitlines()
    seen, names, stems = {}, Counter(), Counter()
    for path in files:
        if path.endswith('.md') or (ROOT / path) == ALLOWED or not (ROOT / path).is_file():
            continue
        seen[path] = tokens((ROOT / path).read_text(errors='ignore'))
        names.update(seen[path][0])
        stems.update(seen[path][1])
    def orphan(path):
        own_names, own_stems = seen.get(path, (set(), set()))
        name, stem = Path(path).name, Path(path).stem
        if names[name] - (name in own_names) > 0 or stems[stem] - (stem in own_stems) > 0:
            return False
        script = str(Path(path).with_suffix('.py'))
        return script == path or script not in seen or orphan(script)
    return [path for path in files if path.startswith('tests/modules/') and not path.endswith('.md') and orphan(path)]


class Orphans(unittest.TestCase):
    def test_no_new_orphans_and_the_list_only_shrinks(self):
        allowed = ALLOWED.read_text().split()
        found = orphans()
        self.assertEqual(sorted(set(found) - set(allowed)), [], 'wire these into a gate or delete them')
        self.assertEqual(sorted(set(allowed) - set(found)), [], 'no longer orphans: remove them from orphans.txt')


if __name__ == '__main__':
    unittest.main()
