#!/usr/bin/env python3
"""Read-only local toolchain, TLS configuration and filesystem preflight."""
import argparse
import datetime
import json
import math
import os
from pathlib import Path
import plistlib
import re
import shutil
import stat
import subprocess
import sys

MIN_FREE_BYTES = 4 * 1024**3
MAX_TEXT = 4096
PYTHON_IDENTITY = r'''
import json, ssl, sys
versions = {}
for name, enum in [('1.2', 'TLSv1_2'), ('1.3', 'TLSv1_3')]:
    row = {'advertised': getattr(ssl, 'HAS_' + enum, None), 'configuration_accepted': False}
    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = context.maximum_version = getattr(ssl.TLSVersion, enum)
        row['configuration_accepted'] = True
    except (AttributeError, ValueError, ssl.SSLError) as error:
        row['error'] = str(error)
    versions[name] = row
print(json.dumps({'executable': sys.executable, 'version': sys.version,
    'ssl_backend': ssl.OPENSSL_VERSION, 'platform': sys.platform, 'tls': versions,
    'scope': 'Local SSLContext configuration only; no socket or handshake'}))
'''
PHP_IDENTITY = "echo json_encode(['version'=>PHP_VERSION,'version_id'=>PHP_VERSION_ID,'zts'=>(bool)PHP_ZTS,'debug'=>(bool)PHP_DEBUG,'integer_bytes'=>PHP_INT_SIZE,'extension_dir'=>PHP_EXTENSION_DIR]);"


def execute(command, timeout=5):
    # Version probes only: no shell, package fetching, Python startup hooks or env output.
    environment = dict(os.environ, RUSTUP_AUTO_INSTALL='0', CARGO_NET_OFFLINE='true')
    return subprocess.run(command, capture_output=True, timeout=timeout, env=environment)


def probe(executable, arguments, timeout=5):
    resolved = shutil.which(str(executable))
    row = {'requested': str(executable), 'resolved': str(Path(resolved).resolve()) if resolved else None,
           'command': [str(executable), *arguments], 'status': 'unavailable'}
    if not resolved:
        row['error'] = 'Executable not found'
        return row
    try:
        result = execute([resolved, *arguments], timeout)
        row.update(returncode=result.returncode,
                   stdout=result.stdout[:MAX_TEXT].decode(errors='replace') if result.returncode == 0 else '',
                   stderr=result.stderr[:MAX_TEXT].decode(errors='replace') if result.returncode == 0 else '',
                   output_truncated=len(result.stdout) > MAX_TEXT or len(result.stderr) > MAX_TEXT)
        if result.returncode == 0 and not row['output_truncated'] and result.stdout.strip():
            row['status'] = 'available'
        elif result.returncode:
            row['error'] = f'Version command exited {result.returncode}; output omitted'
    except (OSError, subprocess.TimeoutExpired) as error:
        row['error'] = type(error).__name__  # Avoid dumping arbitrary inherited environment/error payloads.
    return row


def decode_mount(value):
    return re.sub(r'\\([0-7]{3})', lambda match: chr(int(match[1], 8)), value)


def linux_mounts(text):
    rows = []
    for line in text.splitlines():
        left, separator, right = line.partition(' - ')
        fields, tail = left.split(), right.split()
        if separator and len(fields) > 4 and tail:
            rows.append({'mountpoint': decode_mount(fields[4]), 'filesystem_type': tail[0],
                         'ram_backed': True if tail[0] in ['tmpfs', 'ramfs'] else None,
                         'ram_evidence': 'kernel mountinfo ' + tail[0] if tail[0] in ['tmpfs', 'ramfs'] else None})
    return rows


def darwin_mounts(text, images):
    ram = {entity.get('mount-point') for image in images.get('images', [])
           if str(image.get('image-path', '')).startswith('ram://')
           for entity in image.get('system-entities', [])}
    rows = []
    for line in text.splitlines():
        left, separator, options = line.rpartition(' (')
        _, on, mountpoint = left.partition(' on ')
        if separator and on:
            rows.append({'mountpoint': mountpoint, 'filesystem_type': options.split(',')[0].rstrip(')'),
                         'ram_backed': True if mountpoint in ram else None,
                         'ram_evidence': 'hdiutil ram:// image' if mountpoint in ram else None})
    return rows


def mounts(timeout=5):
    try:
        if sys.platform.startswith('linux'):
            return linux_mounts(Path('/proc/self/mountinfo').read_text()), None
        if sys.platform == 'darwin':
            result = execute(['/sbin/mount'], timeout)
            if result.returncode:
                raise ValueError('mount metadata unavailable')
            images = {}
            try:
                info = execute(['/usr/bin/hdiutil', 'info', '-plist'], timeout)
                if info.returncode == 0:
                    images = plistlib.loads(info.stdout)
            except (OSError, ValueError, subprocess.TimeoutExpired):
                pass  # No RAM inference from a volume name when backing metadata is unavailable.
            return darwin_mounts(result.stdout.decode(errors='replace'), images), None
    except (OSError, ValueError, TypeError, AttributeError, subprocess.TimeoutExpired) as error:
        return [], type(error).__name__
    return [], 'Filesystem metadata unsupported on this platform'


def filesystem(requested, table, timeout=5):
    row = {'requested': str(requested), 'status': 'unavailable'}
    try:
        path = Path(requested).expanduser().resolve()
        ancestor = path
        while True:
            try:
                info = ancestor.stat()
                break
            except FileNotFoundError:
                if ancestor == ancestor.parent:
                    raise
                ancestor = ancestor.parent
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError('Nearest existing path is not a directory')
        usage = shutil.disk_usage(ancestor)
        row.update(resolved=str(path), exists=ancestor == path, measured_at=str(ancestor),
                   device=info.st_dev, total_bytes=usage.total, used_bytes=usage.used,
                   free_bytes=usage.free, minimum_free_bytes=MIN_FREE_BYTES,
                   meets_guard=usage.free >= MIN_FREE_BYTES, status='available')
        candidates = [m for m in table if path == Path(m['mountpoint']) or Path(m['mountpoint']) in path.parents]
        if sys.platform == 'darwin':
            # Firmlinks such as /Users may live on /System/Volumes/Data; prefix guessing is wrong.
            result = execute(['/bin/df', '-P', str(ancestor)], timeout)
            fields = result.stdout.decode(errors='replace').splitlines()[-1].split(maxsplit=5)
            if result.returncode == 0 and len(fields) == 6:
                actual = decode_mount(fields[-1])
                candidates = [m for m in table if m['mountpoint'] == actual]
                row['mountpoint'] = actual
        if candidates:
            row.update(max(candidates, key=lambda m: len(m['mountpoint'])))
        row.setdefault('filesystem_type', None)
        row.setdefault('ram_backed', None)
        row.setdefault('ram_evidence', None)
    except (OSError, ValueError, RuntimeError, IndexError, subprocess.TimeoutExpired) as error:
        row['error'] = str(error) if isinstance(error, ValueError) else type(error).__name__
    return row


def collect(paths, selected, required_tls=('1.2', '1.3'), timeout=5):
    findings = []
    table, mount_error = mounts(timeout)
    filesystems = {name: filesystem(path, table, timeout) for name, path in paths.items()}
    for name, row in filesystems.items():
        if row['status'] != 'available' or (name == 'source' and not row['exists']):
            findings.append({'status': 'unavailable', 'subject': name, 'detail': 'Source/path filesystem unavailable'})
        elif not row['meets_guard']:
            findings.append({'status': 'blocked', 'subject': name,
                             'detail': f"{row['free_bytes']} free bytes; require {MIN_FREE_BYTES}"})
    override = os.environ.get('SWOOLE_RS_MIN_FREE_BYTES')
    configured = MIN_FREE_BYTES
    if override is not None:
        try:
            configured = int(override)
            if configured < 0:
                raise ValueError()
            if configured != MIN_FREE_BYTES:
                findings.append({'status': 'blocked', 'subject': 'guard',
                                 'detail': 'Configured override differs from the unchanged 4 GiB diagnostic threshold'})
        except ValueError:
            configured = None
            findings.append({'status': 'unavailable', 'subject': 'guard', 'detail': 'Invalid numeric guard override'})
    commands = {'python': ['-I', '-S', '-B', '-c', PYTHON_IDENTITY], 'cc': ['--version'],
                'cxx': ['--version'], 'rustc': ['--version', '--verbose'], 'cargo': ['--version'],
                'php': ['-n', '-r', PHP_IDENTITY], 'php_config': ['--version'],
                'php_extension_dir': ['--extension-dir'], 'make': ['--version'], 'openssl': ['version']}
    tools = {name: probe(selected['php_config'] if name == 'php_extension_dir' else selected[name], args, timeout)
             for name, args in commands.items()}
    for name in ['python', 'php']:
        row = tools[name]
        if row['status'] == 'available':
            try:
                row['identity'] = json.loads(row['stdout'])
                identity = row['identity']
                required = ['executable', 'version', 'ssl_backend', 'tls'] if name == 'python' else ['version', 'zts']
                if not isinstance(identity, dict) or any(key not in identity for key in required):
                    raise ValueError()
                if name == 'python' and not isinstance(identity['tls'], dict):
                    raise ValueError()
            except ValueError:
                row.update(status='unavailable', error='Malformed identity JSON')
    for name, row in tools.items():
        if row['status'] != 'available':
            findings.append({'status': 'unavailable', 'subject': name, 'detail': row.get('error', 'Version probe unavailable')})
    if tools['php']['status'] == tools['php_config']['status'] == 'available':
        if tools['php']['identity']['version'] != tools['php_config']['stdout'].strip():
            findings.append({'status': 'blocked', 'subject': 'php/config selection',
                             'detail': 'Selected PHP runtime/config versions differ; compatibility not established'})
    python = tools['python'].get('identity', {}) if tools['python']['status'] == 'available' else {}
    for version in required_tls:
        capability = python.get('tls', {}).get(version, {})
        if not isinstance(capability, dict):
            capability = {}
        if tools['python']['status'] != 'available':
            continue
        if any(type(capability.get(key)) is not bool for key in ['advertised', 'configuration_accepted']):
            findings.append({'status': 'unavailable', 'subject': f'python TLS {version}',
                             'detail': 'TLS capability observation unavailable'})
        elif not (capability['advertised'] and capability['configuration_accepted']):
            detail = capability.get('error', 'Provider advertisement/configuration disagree; no handshake performed')
            findings.append({'status': 'blocked', 'subject': f'python TLS {version}', 'detail': detail})
    status = 'blocked' if any(f['status'] == 'blocked' for f in findings) else 'unavailable' if findings else 'ready'
    return {'schema_version': 1, 'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'status': status, 'passed': status == 'ready', 'platform': sys.platform, 'minimum_free_bytes': MIN_FREE_BYTES,
            'configured_guard_bytes': configured, 'required_tls': list(required_tls),
            'filesystems': filesystems, 'mount_metadata_error': mount_error, 'tools': tools, 'findings': findings,
            'scope': 'Read-only local diagnostic snapshot; no build, network, handshake, mutation or behavior/parity proof. Free bytes are not reserved; unknown RAM backing is null.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['source', 'native', 'output']:
        parser.add_argument(f'--{name}-root', type=Path, required=True)
    defaults = {'python': sys.executable, 'cc': 'cc', 'cxx': 'c++', 'rustc': 'rustc', 'cargo': 'cargo',
                'php': 'php', 'php_config': 'php-config', 'make': 'make', 'openssl': 'openssl'}
    for name, default in defaults.items():
        parser.add_argument('--' + name.replace('_', '-'), default=default)
    parser.add_argument('--require-tls', action='append', choices=['1.2', '1.3'], help='Default: both versions')
    parser.add_argument('--timeout', type=float, default=5)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error('--timeout must be positive')
    report = collect({name: getattr(args, name + '_root') for name in ['source', 'native', 'output']},
                     {name: getattr(args, name) for name in defaults}, args.require_tls or ['1.2', '1.3'], args.timeout)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Environment: {report['status']}; unchanged guard {MIN_FREE_BYTES} bytes")
        for name, row in report['filesystems'].items():
            print(f"{name}: {row.get('resolved', row['requested'])}; measured {row.get('measured_at')}; "
                  f"free={row.get('free_bytes')}/{row.get('total_bytes')}; mount={row.get('mountpoint')}; "
                  f"type={row.get('filesystem_type')}; RAM={row.get('ram_backed')}")
        for name, row in report['tools'].items():
            identity = row.get('identity', row.get('stdout', '').splitlines()[:1])
            print(f"{name}: {row['status']}; {row['resolved']}; {json.dumps(identity)}")
        for finding in report['findings']:
            print(f"{finding['status']}: {finding['subject']}: {finding['detail']}")
        print(report['scope'])
    return {'ready': 0, 'blocked': 1, 'unavailable': 2}[report['status']]


if __name__ == '__main__':
    sys.exit(main())
