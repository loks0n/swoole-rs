"""Check that the engines under test match the build manifest and current clients patch."""
import hashlib
import json
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[3]

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def section(patch,destination):
    result=next((part for part in patch.split('diff --git ') if part.startswith(f'a/{destination} ')),None)
    if result is None:raise ValueError(f'Frozen source lacks converted destination {destination}')
    return result
def attest(manifest_path,source_ref,identities,destination):
    if len(identities)!=2 or {bool(item['rust_feature_bits']&1048576) for item in identities}!={False,True}:
        raise ValueError('Require native and selected clients engines')
    manifest=json.loads(manifest_path.read_text())
    selected=next(item for item in identities if item['rust_feature_bits']&1048576)
    relative='migration/patches/clients/0001-rust-address-client-policy.patch'
    patch=next(item for item in manifest['inputs']['patches'] if item['path']==relative)
    source=subprocess.check_output(['git','show',f'{source_ref}:{relative}'],cwd=ROOT)
    if hashlib.sha256(source).hexdigest()!=patch['sha256']:raise ValueError('Frozen source patch does not match build manifest')
    selected_section=section(source.decode(),destination)
    if selected_section!=section((ROOT/relative).read_text(),destination):raise ValueError('Frozen witnessed source differs from current implementation')
    if selected['sha256']!=manifest['extension_sha256']:raise ValueError('Selected extension does not match manifest')
    if manifest['inputs']['upstream_commit']!='8e8c49915ca5f9dcb9ee654f9e336a9c88dd375e':raise ValueError('Unexpected upstream')
    return dict(source_ref=subprocess.check_output(['git','rev-parse',source_ref],cwd=ROOT,text=True).strip(),destination=destination)
