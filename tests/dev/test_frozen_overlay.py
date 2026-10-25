"""Only an exact frozen repair may precede the destination's sole mutable owner."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from tools.build_hybrid import COMMIT, apply_patch_verified, patches_for
from tools.check_migration import validate

TARGET='src/network/socket.cc'
FROZEN='diff --git a/'+TARGET+' b/'+TARGET+'\n--- a/'+TARGET+'\n+++ b/'+TARGET+'\n@@ -2,2 +2,2 @@\n anchor\n-repair-off\n+repair-on\n'
RUST='diff --git a/'+TARGET+' b/'+TARGET+'\n--- a/'+TARGET+'\n+++ b/'+TARGET+'\n@@ -1,2 +1,2 @@\n-native\n+rust\n anchor\n'


class FrozenOverlay(unittest.TestCase):
    def fixture(self, root):
        modules=[]
        for module_id,folder,body,targets in [('M05','rust',RUST,[TARGET]),('M15','fixed',FROZEN,[])]:
            directory=root/'migration/patches'/folder;directory.mkdir(parents=True)
            path=directory/'change.patch';path.write_text(body)
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            (directory/'manifest.json').write_text(json.dumps(dict(upstream_commit=COMMIT,
                patches=[dict(path=path.name,sha256=digest,upstream_paths=[TARGET])])))
            module=dict(id=module_id,assigned_to='@loks0n',status='in_progress',depends_on=[],
                        owned_paths=[str(directory.relative_to(root))+'/'],upstream_patch_targets=targets)
            if module_id=='M15':
                module['frozen_upstream_patches']=[dict(path=str(path.relative_to(root)),sha256=digest,
                    upstream_paths=[TARGET],target_owner='M05')]
            modules.append(module)
        return modules

    def test_four_profiles_keep_repair_and_rust_selection_independent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);rust,fixed=self.fixture(root)
            validate(dict(modules=[rust,fixed],dependency_ready=[]))
            for label,modules,expected in [('native',[],'native\nanchor\nrepair-off\n'),
                    ('fixed-native',[fixed],'native\nanchor\nrepair-on\n'),
                    ('rust',[rust],'rust\nanchor\nrepair-off\n'),
                    ('fixed-rust',[rust,fixed],'rust\nanchor\nrepair-on\n')]:
                with self.subTest(profile=label):
                    rows=patches_for(modules,root=root)
                    if len(rows)==2:self.assertEqual(rows[0]['frozen_overlay_for'],'M05')
                    tree=root/label;path=tree/TARGET;path.parent.mkdir(parents=True);path.write_text('native\nanchor\nrepair-off\n')
                    for row in rows:apply_patch_verified(tree,root/row['path'],row['upstream_paths'],row['sha256'])
                    self.assertEqual(path.read_text(),expected)

    def mixed_fixture(self, root):
        rust, fixed = self.fixture(root)
        other = 'src/server/base.cc'
        entry = fixed['frozen_upstream_patches'][0]
        path = root / entry['path']
        path.write_text(FROZEN + FROZEN.replace(TARGET, other))
        entry.update(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), upstream_paths=[TARGET, other],
                     target_owners={TARGET: 'M05', other: 'M15'})
        del entry['target_owner']
        fixed['upstream_patch_targets'] = [other]
        (path.parent / 'manifest.json').write_text(json.dumps(dict(upstream_commit=COMMIT,
            patches=[dict(path=path.name, sha256=entry['sha256'], upstream_paths=entry['upstream_paths'])])))
        return rust, fixed, other

    def test_one_frozen_patch_can_retain_its_own_file_and_transfer_another(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rust, fixed, other = self.mixed_fixture(root)
            validate(dict(modules=[rust, fixed], dependency_ready=[]))
            for label, modules in [('native', []), ('fixed', [fixed]), ('rust', [rust]), ('both', [rust, fixed])]:
                tree = root / label
                for target in [TARGET, other]:
                    p = tree / target; p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text('native\nanchor\nrepair-off\n')
                rows = patches_for(modules, root=root)
                if fixed in modules:
                    self.assertEqual(rows[0]['frozen_overlay_for'], {TARGET: 'M05', other: 'M15'})
                for row in rows:
                    apply_patch_verified(tree, root / row['path'], row['upstream_paths'], row['sha256'])
                repair = 'repair-on' if fixed in modules else 'repair-off'
                self.assertEqual((tree / TARGET).read_text(), ('rust' if rust in modules else 'native') + '\nanchor\n' + repair + '\n')
                self.assertEqual((tree / other).read_text(), 'native\nanchor\n' + repair + '\n')
            with self.assertRaisesRegex(ValueError, 'Multiple patches'):
                patches_for([fixed, rust, rust], root=root)

    def test_mixed_owner_contract_requires_complete_unambiguous_reserved_targets(self):
        for mutation in ['missing', 'extra', 'unknown', 'wrong-reservation', 'ambiguous', 'all-self', 'duplicate']:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                rust, fixed, other = self.mixed_fixture(root)
                entry = fixed['frozen_upstream_patches'][0]
                owners = entry['target_owners']
                if mutation == 'missing': del owners[other]
                if mutation == 'extra': owners['src/unreserved.cc'] = 'M05'
                if mutation == 'unknown': owners[other] = 'M99'
                if mutation == 'wrong-reservation': owners[other] = 'M05'
                if mutation == 'ambiguous': entry['target_owner'] = 'M05'
                if mutation == 'all-self': owners[TARGET] = 'M15'
                if mutation == 'duplicate': entry['upstream_paths'].append(TARGET)
                with self.assertRaisesRegex(ValueError, 'frozen overlay'):
                    validate(dict(modules=[rust, fixed], dependency_ready=[]))

    def test_changed_frozen_bytes_or_removed_patch_refuse(self):
        for mutation in ['bytes','removed']:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);rust,fixed=self.fixture(root)
                entry=fixed['frozen_upstream_patches'][0];path=root/entry['path'];manifest=path.parent/'manifest.json'
                data=json.loads(manifest.read_text())
                if mutation=='removed':data['patches']=[]
                else:
                    path.write_text(FROZEN.replace('repair-on','different'))
                    data['patches'][0]['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
                manifest.write_text(json.dumps(data))
                with self.assertRaisesRegex(ValueError,'[Ff]rozen overlay'):
                    patches_for([rust,fixed],root=root)

    def test_unrelated_overlap_and_third_patch_remain_forbidden(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);rust,fixed=self.fixture(root)
            unrelated=deepcopy(rust);unrelated['id']='M99'
            with self.assertRaisesRegex(ValueError,'Multiple patches'):
                patches_for([fixed,unrelated],root=root)
            with self.assertRaisesRegex(ValueError,'Multiple patches'):
                patches_for([fixed,rust,rust],root=root)
            with self.assertRaisesRegex(ValueError,'conflicting'):
                validate(dict(modules=[rust,fixed,unrelated],dependency_ready=[]))

    def test_frozen_contract_cannot_expand_paths_or_invent_an_owner(self):
        for mutation in ['owner','target','path','hash']:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);modules=self.fixture(root);entry=modules[1]['frozen_upstream_patches'][0]
                if mutation=='owner':entry['target_owner']='unknown'
                if mutation=='target':entry['upstream_paths']=['../other.cc']
                if mutation=='path':entry['path']='migration/patches/fixed-other/change.patch'
                if mutation=='hash':entry['sha256']='short'
                with self.assertRaisesRegex(ValueError,'frozen overlay'):
                    validate(dict(modules=modules,dependency_ready=[]))
