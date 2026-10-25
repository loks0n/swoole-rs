#!/usr/bin/env python3
"""Explicit Redis-enabled original Table/Channel profile; baseline stays separate."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
import uuid

from gate import ROOT, PIN, sha
from tools.harness import write_report
from tools.build_upstream import require_build_space
from corpus.upstream.tree import inventory


class ManagedRedis:
    """One owned ephemeral service, never an ambient endpoint or database."""
    def __init__(self, work, record, *, image=None, server=None, cli=None):
        self.work, self.record = work, record
        self.image, self.server, self.cli = image, server, cli
        self.container = self.network = self.process = self.log = None
        self.port = self.run_id = None
        record.update(commands=[], removed=False)

    def command(self, args, *, check=True, timeout=20):
        result = subprocess.run(list(map(str, args)), capture_output=True, text=True, timeout=timeout)
        self.record['commands'].append(dict(command=list(map(str, args)), exit=result.returncode,
                                           stdout=result.stdout, stderr=result.stderr))
        if check and result.returncode:
            raise ValueError('Private Redis command failed; raw output retained')
        return result

    def observe(self):
        if self.image:
            command = ['docker', 'exec', self.container, 'redis-cli', '--raw', 'INFO', 'server']
        else:
            if self.process.poll() is not None:
                raise ValueError('Owned Redis process exited')
            command = [self.cli, '-h', '127.0.0.1', '-p', str(self.port), '--raw', 'INFO', 'server']
        result = self.command(command, check=False, timeout=2)
        fields = dict(line.split(':', 1) for line in result.stdout.splitlines()
                      if ':' in line and not line.startswith('#'))
        if result.returncode or not fields.get('run_id'):
            return None
        if not self.image and fields.get('process_id') != str(self.process.pid):
            raise ValueError('Private port does not belong to the managed Redis PID')
        return {key: fields.get(key) for key in ['run_id', 'process_id', 'redis_version']}

    def __enter__(self):
        try:
            if self.image:
                if not re.fullmatch(r'sha256:[0-9a-f]{64}', self.image):
                    raise ValueError('Docker Redis requires an immutable sha256 image ID')
                image = json.loads(self.command(['docker', 'image', 'inspect', self.image]).stdout)[0]
                if image['Id'] != self.image:
                    raise ValueError('Docker image identity differs')
                self.record['image'] = {key: image.get(key) for key in ['Id', 'RepoDigests', 'Architecture']}
                network_name = 'swoole-m27-' + uuid.uuid4().hex
                self.command(['docker', 'network', 'create', network_name])
                self.network = network_name
                self.container = network_name + '-redis'
                # Docker forwarding reaches the container via its private bridge.
                # Publish only an ephemeral host loopback endpoint; no auth is
                # added because the unchanged original fixture does not log in.
                command = ['docker', 'run', '-d', '--rm', '--name', self.container, '--network', self.network,
                           '-p', '127.0.0.1::6379/tcp', '--memory', '128m', '--pids-limit', '64',
                           self.image, 'redis-server', '--save', '', '--appendonly', 'no',
                           '--bind', '0.0.0.0', '--protected-mode', 'no']
                self.container = self.command(command).stdout.strip()
                info = json.loads(self.command(['docker', 'inspect', self.container]).stdout)[0]
                ports = info['NetworkSettings']['Ports'].get('6379/tcp')
                if (info['Image'] != self.image or not ports or len(ports) != 1 or
                        ports[0]['HostIp'] != '127.0.0.1'):
                    raise ValueError('Redis container/image/loopback publication differs')
                self.port = int(ports[0]['HostPort'])
                network = json.loads(self.command(['docker', 'network', 'inspect', self.network]).stdout)[0]
                if set(network.get('Containers', {})) != {self.container}:
                    raise ValueError('Redis network is not exclusively owned by this profile')
                self.record.update(container=self.container, network=self.network,
                                   image_id=info['Image'], port_bindings=ports, network_id=network['Id'])
            else:
                self.server = shutil.which(str(self.server or 'redis-server'))
                self.cli = shutil.which(str(self.cli or 'redis-cli'))
                if not self.server or not self.cli:
                    raise ValueError('Configured native redis-server and redis-cli prerequisites are missing')
                self.record['binaries'] = dict(server=self.server, cli=self.cli)
                with socket.socket() as reservation:
                    reservation.bind(('127.0.0.1', 0))
                    self.port = reservation.getsockname()[1]
                self.log = (self.work / 'redis.log').open('w')
                command = [self.server, '--bind', '127.0.0.1', '--protected-mode', 'yes',
                           '--port', str(self.port), '--save', '', '--appendonly', 'no',
                           '--daemonize', 'no', '--dir', str(self.work)]
                self.record['start_command'] = command
                self.process = subprocess.Popen(command, stdout=self.log, stderr=subprocess.STDOUT)
                self.record['pid'] = self.process.pid
            if self.port == 6379:
                raise ValueError('Refusing the shared Redis port')
            self.record['endpoint'] = dict(host='127.0.0.1', port=self.port)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                identity = self.observe()
                if identity:
                    self.run_id = identity['run_id']
                    self.record['identity_before'] = identity
                    return self
                time.sleep(.05)
            raise ValueError('Private Redis readiness timed out')
        except BaseException:
            self.close()
            raise

    def verify(self):
        identity = self.observe()
        if not identity or identity['run_id'] != self.run_id:
            raise ValueError('Managed Redis identity changed during original qualification')
        self.record['identity_after'] = identity

    def close(self):
        errors = self.record.setdefault('cleanup_errors', [])
        if self.process:
            try:
                if self.process.poll() is None:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait(timeout=5)
                self.record['exit'] = self.process.returncode
                self.record['removed'] = self.process.poll() is not None
            except Exception as error:
                errors.append(str(error))
        if self.log:
            self.log.close()
            raw = self.work / 'redis.log'
            self.record['log'] = raw.read_text(errors='replace')
        if self.container:
            try:
                self.command(['docker', 'rm', '-f', self.container], check=False)
                selector = ('id=' + self.container if re.fullmatch('[0-9a-f]{64}', self.container)
                            else 'name=^/' + self.container + '$')
                listed = self.command(['docker', 'ps', '-aq', '--filter', selector])
                self.record['removed'] = not listed.stdout.strip()
            except Exception as error:
                errors.append(str(error))
        if self.network:
            try:
                self.command(['docker', 'network', 'rm', self.network], check=False)
                listed = self.command(['docker', 'network', 'ls', '-q', '--filter', 'name=^' + self.network + '$'])
                self.record['network_removed'] = not listed.stdout.strip()
            except Exception as error:
                errors.append(str(error))

    def __exit__(self, *_):
        self.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--source-ref', required=True)
    parser.add_argument('--engine', action='append', required=True)
    parser.add_argument('--build-manifest', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[])
    parser.add_argument('--redis-extension', type=Path, required=True)
    parser.add_argument('--redis-image', help='Immutable sha256 ID; otherwise managed native server/cli')
    parser.add_argument('--redis-server', type=Path)
    parser.add_argument('--redis-cli', type=Path)
    parser.add_argument('--case', action='append', default=[], help='Explicit supplemental selection; default all63 originals')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    work = output.parent / ('phpcollections-originals-' + uuid.uuid4().hex)
    work.mkdir(parents=True)
    report = dict(passed=False, scope=__doc__, profile='redis-enabled', pin=PIN, source_ref=args.source_ref,
                  work=str(work), commands=[], service={},
                  baseline_replaced=False, full_original_inventory_passed=False, performance_measured=False)
    def run(command, *, env=None):
        result = subprocess.run(list(map(str, command)), env=env, text=True, capture_output=True)
        report['commands'].append(dict(command=list(map(str, command)), exit=result.returncode,
                                       stdout=result.stdout, stderr=result.stderr))
        write_report(output, report)
        return result
    try:
        require_build_space(ROOT)
        require_build_space(work)
        if not args.redis_extension.is_file():
            raise ValueError('Matching Redis PHP extension prerequisite is missing')
        if args.redis_image and (args.redis_server or args.redis_cli):
            raise ValueError('Choose native Redis binaries or Docker image, not both')
        probe_flags = [flag for name in [*args.php_extension, str(args.redis_extension.resolve())]
                       for flag in ['-d', 'extension=' + name]]
        probe = run([args.php, '-n', *probe_flags, '-r',
                     'echo json_encode(["php"=>PHP_VERSION,"redis"=>phpversion("redis"),"class"=>class_exists("Redis"),"extension_dir"=>PHP_EXTENSION_DIR]);'])
        if probe.returncode or probe.stderr:
            raise ValueError('Redis PHP extension prerequisite failed to load')
        metadata = json.loads(probe.stdout)
        if not metadata.get('class') or not metadata.get('redis'):
            raise ValueError('Loaded PHP extension does not provide Redis')
        report['redis_extension'] = dict(path=str(args.redis_extension.resolve()), **metadata)
        report['extra_php_extensions'] = []
        for name in args.php_extension:
            path = Path(name) if Path(name).is_absolute() else Path(metadata['extension_dir']) / (name + '.so')
            report['extra_php_extensions'].append(dict(flag=name, path=str(path)))
        manifests = [inventory(args.source, group, 'phpcollections', ['upstream_test_bootstrap', capability])
                     for group, capability in [('swoole_table', 'table'), ('swoole_channel_coro', 'coroutines')]]
        tests = [case for item in manifests for case in item['tests']]
        support = {}
        for item in manifests:
            for row in item['support_files']:
                if row['path'] in support and support[row['path']] != row:
                    raise ValueError('Original support identities conflict')
                support[row['path']] = row
        available = {case['path'] for case in tests}
        if len(set(args.case)) != len(args.case) or not set(args.case) <= available:
            raise ValueError('Supplemental case selection is duplicate or outside the complete original inventory')
        manifest = dict(repository=manifests[0]['repository'], commit=PIN, tests=tests,
                        support_files=sorted(support.values(), key=lambda row: row['path']))
        manifest_path = work / 'complete-originals.json'
        write_report(manifest_path, manifest)
        report['inventory'] = dict(cases=len(tests), support_blobs=len(support),
                                   selected=args.case or sorted(available), full_selection=not args.case)
        flags = [flag for name in [*args.php_extension, str(args.redis_extension.resolve())]
                 for flag in ['--php-extension', name]]
        engines = [flag for engine in args.engine for flag in ['--engine', engine]]
        runtime_output = work / 'runtime.json'
        runtime_command = [sys.executable, ROOT / 'tests/modules/phpcollections/php_runtime.py',
                           '--php', args.php, *flags, *engines, '--build-manifest', args.build_manifest,
                           '--archive', args.archive, '--source-ref', args.source_ref, '--output', runtime_output]
        if run(runtime_command).returncode:
            raise ValueError('Current source-attested runtime prerequisite failed; original profile not run')
        runtime = json.loads(runtime_output.read_text())
        if not runtime['passed']:
            raise ValueError('Current runtime receipt did not pass')
        report['runtime'] = dict(path=str(runtime_output),
                                source_attestation=runtime['source_attestation'], engines=runtime['engines'])
        copied_engines = [flag for engine in runtime['engines']
                          for flag in ['--engine', engine['name'] + '=' + engine['extension']]]
        with ManagedRedis(work, report['service'], image=args.redis_image,
                          server=args.redis_server, cli=args.redis_cli) as service:
            env = {**os.environ, 'REDIS_SERVER_HOST': '127.0.0.1', 'REDIS_SERVER_PORT': str(service.port)}
            original_output = work / 'originals.json'
            result = run([sys.executable, ROOT / 'corpus/upstream/run.py', '--source', args.source,
                          '--manifest', manifest_path, '--php', args.php, *flags, *copied_engines,
                          *[flag for case in args.case for flag in ['--case', case]],
                          '--require-all', '--isolate-cases', '--timeout', '90', '--output', original_output], env=env)
            service.verify()
            if original_output.is_file():
                report['originals'] = dict(path=str(original_output),
                                           receipt=json.loads(original_output.read_text()))
            if result.returncode:
                raise ValueError('Redis-enabled originals failed/skipped/unsupported; first outputs retained')
        for engine in runtime['engines']:
            if sha(engine['extension']) != engine['sha256']:
                raise ValueError('Copied engine changed during original qualification')
        if (report['service']['cleanup_errors'] or not report['service']['removed'] or
                (args.redis_image and not report['service'].get('network_removed'))):
            raise ValueError('Managed Redis teardown not verified')
        report['passed'] = True
        report['full_original_inventory_passed'] = not args.case
    except BaseException as error:
        report['error'] = f'{type(error).__name__}: {error}'
        if not isinstance(error, Exception):
            raise
    finally:
        write_report(output, report)
    print(json.dumps({key: report.get(key) for key in ['passed', 'error', 'work']}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
