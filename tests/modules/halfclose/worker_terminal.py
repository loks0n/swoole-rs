#!/usr/bin/env python3
"""Observe an in-flight HTTP response across private worker death or graceful replacement."""
import argparse
from contextlib import ExitStack, closing
import http.client
import json
import os
from pathlib import Path
import signal
import socket
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import parse_engines, request, server, write_report
from tests.modules.halfclose.gate import require
from tests.modules.halfclose.pipeline_concurrency import PipelineSocket

def wait_file(path, predicate):
    deadline = time.monotonic() + 4
    while True:
        if path.exists():
            value = json.loads(path.read_text())
            if predicate(value):
                return value
        require(time.monotonic() < deadline, f'worker state timeout: {path.name}')
        time.sleep(.01)

def run(engine, kill_worker, row, drain_worker=False, kill_retiring=False, exit_zero=False):
    replace_worker = kill_worker or drain_worker or exit_zero
    cancel_response = kill_worker or kill_retiring or exit_zero
    with tempfile.TemporaryDirectory(prefix='http-worker-terminal-') as directory:
        directory = Path(directory)
        with server(engine, Path(__file__).with_suffix('.php'),
                    {'TEST_DATA': str(directory), 'TEST_HOLD_SECONDS': '10' if kill_worker or exit_zero else '.05',
                     'TEST_DRAIN': str(int(drain_worker)), 'TEST_EXIT_ZERO': str(int(exit_zero))}) as (port, proc):
            with ExitStack() as resources:
                connection = resources.enter_context(socket.create_connection(('127.0.0.1', port), timeout=3))
                if replace_worker:
                    idle = resources.enter_context(closing(http.client.HTTPConnection('127.0.0.1', port, timeout=3)))
                    idle.request('GET', '/health', headers={'Connection': 'keep-alive'})
                    response = idle.getresponse()
                    require(response.status == 200 and response.read() == b'ready', 'idle connection setup failed')
                    idle_socket = idle.sock
                    idle_address = idle_socket.getsockname()
                connection.sendall(b'GET /hold HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
                row['hold'] = wait_file(directory / 'hold.json', lambda value: value.get('started'))
                worker = row['hold']['pid']
                if replace_worker:
                    row['master_pid'] = proc.pid
                    row['worker_group'] = os.getpgid(worker)
                    require(worker != proc.pid and row['worker_group'] == os.getpgid(proc.pid) == proc.pid,
                            'worker is not in the isolated test server process group')
                    if exit_zero:
                        # A distinct request exits the same fixed worker while /hold is suspended.
                        with socket.create_connection(('127.0.0.1', port), timeout=3) as trigger:
                            trigger.sendall(b'GET /exit-zero HTTP/1.1\r\nHost: localhost\r\n\r\n')
                            row['exit_trigger'] = wait_file(directory / 'exit-zero.json', lambda value: True)
                            require(row['exit_trigger'] == {'pid': worker, 'status': 0, 'function': 'libc _exit'},
                                    'exit trigger did not execute in the held response worker')
                    elif kill_worker:
                        os.kill(worker, signal.SIGKILL)
                        row['signal_sent'] = 'SIGKILL'
                    else:
                        status, _, body = request(port, '/stop')
                        require(status == 200 and body == b'stopping', 'worker stop request failed')
                        row['stop_request'] = wait_file(directory / 'stop.json', lambda value: value.get('accepted'))
                    row['respawn'] = wait_file(directory / 'ready.json', lambda value: value['pid'] != worker)
                    status, _, body = request(port, '/health')
                    row['new_worker_health'] = {'status': status, 'body': body.decode()}
                    require(status == 200 and body == b'ready', 'replacement worker is not serving')
                    idle.request('GET', '/health', headers={'Connection': 'keep-alive'})
                    response = idle.getresponse()
                    body = response.read()
                    row['healthy_idle_after'] = {'status': response.status, 'body': body.decode(),
                                                 'same_socket': idle.sock is idle_socket,
                                                 'same_local_address': idle.sock is not None and idle.sock.getsockname() == idle_address}
                    require(response.status == 200 and body == b'ready' and row['healthy_idle_after']['same_socket']
                            and row['healthy_idle_after']['same_local_address'], 'healthy idle session did not survive worker respawn')
                    if drain_worker:
                        status, _, body = request(port, '/identity')
                        row['replacement_identity'] = int(body)
                        require(status == 200 and row['replacement_identity'] == row['respawn']['pid'],
                                'replacement worker did not serve identity request')
                        row['old_worker_alive_before_release'] = os.getpgid(worker) == proc.pid
                        row['old_response_finished_before_release'] = (directory / 'finished.json').exists()
                        require(row['old_worker_alive_before_release'] and not row['old_response_finished_before_release'],
                                'graceful replacement did not overlap the pending old response')
                        if kill_retiring:
                            os.kill(worker, signal.SIGKILL)
                            row['signal_sent'] = 'SIGKILL'
                            row['retiring_worker_killed_before_release'] = True
                        else:
                            (directory / 'release').touch()
                    connection.settimeout(1 if cancel_response else 3)
                parts = []
                try:
                    while True:
                        part = connection.recv(8192)
                        if not part:
                            break
                        parts.append(part)
                    row['client_terminal'] = True
                except socket.timeout:
                    row['client_terminal'] = False
                raw = b''.join(parts)
                row['bytes'] = len(raw)
                if kill_retiring:
                    status, _, body = request(port, '/identity')
                    row['replacement_identity_after_kill'] = int(body)
                    require(status == 200 and row['replacement_identity_after_kill'] == row['respawn']['pid'],
                            'current worker changed after retiring worker termination')
                require(row['client_terminal'], 'in-flight client remained open after worker terminal state')
                if raw:
                    response = http.client.HTTPResponse(PipelineSocket(raw))
                    response.begin()
                    body = response.read()
                    row['response'] = {'status': response.status, 'body': body.decode()}
                    if cancel_response:
                        require(500 <= response.status < 600, 'dead worker request resumed as successful output')
                    else:
                        require(response.status == 200 and body == b'complete', 'normal response changed')
                else:
                    require(cancel_response, 'normal response was lost')
                require(proc.poll() is None, 'server master exited')
                if drain_worker and not kill_retiring:
                    row['finished'] = wait_file(directory / 'finished.json', lambda value: value.get('accepted'))
                    require(row['finished']['pid'] == worker, 'old worker did not complete its retained response')

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--engine', action='append', required=True)
    p.add_argument('--php', default='php')
    p.add_argument('--php-extension', action='append', default=[])
    transitions = p.add_mutually_exclusive_group()
    transitions.add_argument('--probe-worker-kill', action='store_true', help='Signal only the verified isolated test worker; preserve failures')
    transitions.add_argument('--probe-worker-drain', action='store_true', help='Require retiring worker response after replacement serves new work')
    transitions.add_argument('--probe-retiring-worker-kill', action='store_true', help='Terminate only verified retiring test worker after replacement serves; preserve failures')
    transitions.add_argument('--probe-worker-exit-zero', action='store_true', help='Execute libc _exit(0) in isolated worker with suspended response; requires PHP FFI')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    r = {'scope': 'Actual private PROCESS HTTP coroutine response and managed respawn; no production token/control implementation or all-exit-mode proof',
         'observation': ('Native libc _exit(0) in held response worker; one-second client read after confirmed replacement and healthy idle session'
                         if a.probe_worker_exit_zero else 'Old worker held through graceful replacement, then SIGKILL before release; one-second client read and replacement identity rechecked'
                         if a.probe_retiring_worker_kill else 'Old response held by explicit file barrier until replacement identity and healthy idle session verified; release then require old worker response'
                         if a.probe_worker_drain else 'One-second client read after confirmed respawn and healthy idle session; not an infinite-hang claim'
                         if a.probe_worker_kill else 'Normal completed response control'),
         'worker_exit_zero': a.probe_worker_exit_zero, 'worker_kill': a.probe_worker_kill, 'worker_drain': a.probe_worker_drain,
         'retiring_worker_kill': a.probe_retiring_worker_kill, 'engines': [], 'results': []}
    for e in parse_engines(a.engine, a.php, a.php_extension):
        r['engines'].append(e.metadata())
        row = {'engine': e.name, 'passed': False}
        try:
            run(e, a.probe_worker_kill, row, a.probe_worker_drain or a.probe_retiring_worker_kill, a.probe_retiring_worker_kill, a.probe_worker_exit_zero)
            row['passed'] = True
        except Exception as error:
            row['error'] = f'{type(error).__name__}: {error}'
        r['results'].append(row)
        write_report(a.output, r)
        print(json.dumps(row), flush=True)
    return int(any(not row['passed'] for row in r['results']))

if __name__ == '__main__':
    raise SystemExit(main())
