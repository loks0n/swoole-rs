#!/usr/bin/env python3
"""Actual PHP ephemeral TCP listener, framing callback, response and shutdown; originals separate."""
import argparse
import hashlib
import json
from pathlib import Path
import selectors
import socket
import struct
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.harness import parse_engines,stop_process_group,write_report


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def attest(manifest,archive,source_ref,metadata):
    data=json.loads(manifest.read_text());archive_hash=sha(archive)
    candidates=[m for m in metadata if m['rust_feature_bits']&8388608]
    if len(candidates)!=1 or candidates[0]['sha256']!=data['extension_sha256']:raise ValueError('Manifest does not identify exactly one actual M25 candidate')
    if not data['migrated_feature_bits']&8388608 or 'ports' not in data['inputs']['modules']:raise ValueError('Manifest lacks expected M25 feature8388608')
    if data['inputs']['rust_archive_sha256']!=archive_hash:raise ValueError('Selected archive does not match build manifest')
    module_source=data['inputs']['rust_sources_sha256']['crates/ports/src/lib.rs']
    if module_source!=sha(ROOT/'crates/ports/src/lib.rs'):raise ValueError('Manifest M25 source differs from this current socket-controller consumer')
    caller_digests={k:v for k,v in data['inputs']['headers_sha256'].items() if k.startswith('native/ports/')}
    caller_digests.update({item['path']:item['sha256'] for item in data['inputs']['patches'] if item['path'].startswith('migration/patches/ports/')})
    expected={'native/ports/swoole_rs_ports.h','migration/patches/ports/0001-port.patch','migration/patches/ports/0002-swoole_server_port.patch'}
    if set(caller_digests)!=expected or any(sha(ROOT/path)!=digest for path,digest in caller_digests.items()):raise ValueError('Manifest M25 header/callers differ from current socket-controller consumer')
    export=manifest.parent/'export.json'
    if export.exists():
        identity=json.loads(export.read_text())
        if identity['source_ref']!=source_ref:raise ValueError('Export source reference differs')
        expected=identity['files']
        if expected['build-manifest.json']['sha256']!=sha(manifest) or expected['libswoole_rs_ffi.a']['sha256']!=archive_hash or expected['swoole.so']['sha256']!=candidates[0]['sha256']:raise ValueError('Immutable export identities differ')
        kind='immutable producer export'
    else:
        blob=subprocess.check_output(['git','-C',str(ROOT),'show',source_ref+':crates/ports/src/lib.rs'])
        if hashlib.sha256(blob).hexdigest()!=module_source:raise ValueError('Frozen source reference differs from manifest M25 source')
        kind='frozen Git M25 source blob'
    symbols=subprocess.check_output(['nm','-g',candidates[0]['extension']],text=True,stderr=subprocess.DEVNULL)
    defined={parts[-1].lstrip('_') for line in symbols.splitlines() if len(parts:=line.split())>=2 and parts[-2].upper() in {'T','W'}}
    required=['number','protocol','protocol_name','event','listen_step','socket_step','protocol_plan','connection_count','framing_settings','stream_settings','defaults','callback_property','flag_setting','buffer_setting','packet_eof','packet_width','packet_offset','option','tls_option','tls_value','sni_plan','callback_hook']
    if not all('swr_v1_ports_'+name in defined for name in required):raise ValueError('Actual candidate DSO lacks required M25 controller exports')
    return {'passed':True,'source_ref':source_ref,'source_reference':kind,'required_candidate_dso_exports':required}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--engine',action='append',required=True);p.add_argument('--php',default='php');p.add_argument('--php-extension',action='append',default=[]);p.add_argument('--output',type=Path,required=True);p.add_argument('--build-manifest',type=Path);p.add_argument('--archive',type=Path);p.add_argument('--source-ref');p.add_argument('--protocol',action='append',choices=['length','eof','mqtt']);a=p.parse_args()
    if any([a.build_manifest,a.archive,a.source_ref]) and not all([a.build_manifest,a.archive,a.source_ref]):p.error('Build manifest, archive and source ref are required together')
    script=Path(__file__).with_suffix('.php');report={'scope':__doc__,'engines':[],'results':[],'passed':False,'socket_creation_revision_attested':False,'protocol_inventory':['length','eof','mqtt'],'unmeasured_protocols':[name for name in ['length','eof','mqtt'] if a.protocol and name not in a.protocol]}
    engines=parse_engines(a.engine,a.php,a.php_extension);report['engines']=[engine.metadata() for engine in engines]
    if a.build_manifest:
        try:report['candidate_attestation']=attest(a.build_manifest,a.archive,a.source_ref,report['engines']);report['socket_creation_revision_attested']=True
        except Exception as error:report['candidate_attestation']={'passed':False,'error':str(error)};write_report(a.output,report);return 1
    for engine in engines:
        for protocol in a.protocol or ['length','eof','mqtt']:
            row={'engine':engine.name,'protocol':protocol,'command':engine.command(script,protocol),'passed':False};report['results'].append(row)
            proc=subprocess.Popen(row['command'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
            output=b'';pending=b'';selector=selectors.DefaultSelector();selector.register(proc.stdout,selectors.EVENT_READ)
            try:
                deadline=time.monotonic()+15;ready=None
                while ready is None and time.monotonic()<deadline:
                    if not selector.select(max(0,deadline-time.monotonic())):break
                    chunk=proc.stdout.read1(4096)
                    if not chunk:break
                    output+=chunk;pending+=chunk
                    while b'\n' in pending:
                        line,pending=pending.split(b'\n',1)
                        if line.startswith(b'READY '):ready=json.loads(line[6:])
                if not ready or not 0<ready['port']<65536:raise RuntimeError('ephemeral listener did not become ready')
                payload={'length':struct.pack('!I',13)+b'ports-runtime','eof':b'ports-runtime\r\n','mqtt':b'\x30\x03\x00\x01a'}[protocol];received=b''
                with socket.create_connection(('127.0.0.1',ready['port']),timeout=5) as client:
                    client.sendall(payload[:2]);client.sendall(payload[2:])
                    while len(received)<len(payload):
                        chunk=client.recv(len(payload)-len(received))
                        if not chunk:break
                        received+=chunk
                tail,_=proc.communicate(timeout=10);output+=tail
                row.update(exit=proc.returncode,response_hex=received.hex(),passed=proc.returncode==0 and received==payload and b'OBSERVED framed-receive send shutdown' in output)
            except Exception as error:row['error']=str(error)
            finally:
                selector.close();stop_process_group(proc)
                if proc.stdout and not proc.stdout.closed:output+=proc.stdout.read();proc.stdout.close()
                row['stdout']=output.decode(errors='replace')
            write_report(a.output,report)
    report['backend_comparison_present']={bool(e['rust_feature_bits']&8388608) for e in report['engines']}=={False,True}
    report['passed']=bool(report['results']) and not report['unmeasured_protocols'] and all(r['passed'] for r in report['results']);write_report(a.output,report);print(json.dumps({'passed':report['passed'],'results':report['results']}));return int(not report['passed'])


if __name__=='__main__':sys.exit(main())
