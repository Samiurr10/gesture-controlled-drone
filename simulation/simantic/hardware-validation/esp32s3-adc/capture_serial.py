#!/usr/bin/env python3
"""Capture one ADC command without flashing or resetting the board."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import time
import serial

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--port', required=True)
p.add_argument('--channel', type=int, default=0, choices=range(10))
p.add_argument('--attenuation', type=int, default=3, choices=range(4))
p.add_argument('--count', type=int, default=64)
p.add_argument('--input-mv', type=float, help='measured input, or 0 for confirmed ground')
p.add_argument('--note', default='input condition not recorded')
p.add_argument('--elf', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
p.add_argument('--timeout', type=float, default=30)
a = p.parse_args()
if not 1 <= a.count <= 1024: p.error('count must be 1..1024')
a.out.mkdir(parents=True, exist_ok=False)
lines = []
records = []
command = f'read {a.channel} {a.attenuation} {a.count}'
with serial.Serial(port=None, baudrate=115200, timeout=0.2, exclusive=True) as link:
    link.dtr = False
    link.rts = False
    link.port = a.port
    link.open()
    # Some USB bridges reset at open despite preselected DTR/RTS levels.
    # Let boot finish, then identify the command parser with an explicit query.
    time.sleep(1.0)
    link.reset_input_buffer()
    link.write(b'info\n')
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        line = link.readline().decode('utf-8', errors='replace').strip()
        if not line: continue
        lines.append(line)
        try: item = json.loads(line)
        except json.JSONDecodeError: continue
        records.append(item)
        if item.get('type') == 'info': break
    if not any(x.get('type') == 'info' and x.get('fixture') == 'palmpilot-adc-v1' for x in records):
        (a.out / 'uart.txt').write_text('\n'.join(lines) + '\n')
        raise SystemExit('ADC fixture did not identify itself; no measurement command sent')
    link.write((command + '\n').encode())
    deadline = time.monotonic() + a.timeout
    while time.monotonic() < deadline:
        line = link.readline().decode('utf-8', errors='replace').strip()
        if not line: continue
        lines.append(line)
        try: item = json.loads(line)
        except json.JSONDecodeError: continue
        records.append(item)
        if item.get('type') in ('end', 'error'): break
(a.out / 'uart.txt').write_text('\n'.join(lines) + '\n')
samples = [x for x in records if x.get('type') == 'sample']
begins = [x for x in records if x.get('type') == 'begin']
ends = [x for x in records if x.get('type') == 'end']
valid = (len(begins) == 1 and len(ends) == 1 and len(samples) == a.count
         and begins[0].get('channel') == a.channel and begins[0].get('attenuation') == a.attenuation
         and begins[0].get('count') == a.count and ends[0].get('successful') == a.count
         and ends[0].get('requested') == a.count and ends[0].get('batch') == begins[0].get('batch')
         and all(x.get('batch') == begins[0].get('batch') and x.get('index') == i
                 and x.get('status') == 0 and 0 <= x.get('raw', -1) <= 4095
                 for i, x in enumerate(samples)))
raw = [s['raw'] for s in samples if s.get('status') == 0]
summary = {
    'captured_utc': datetime.now(timezone.utc).isoformat(), 'platform': 'physical ESP32-S3',
    'command': command, 'input_mv': a.input_mv, 'input_note': a.note,
    'local_reference_elf_sha256': hashlib.sha256(a.elf.read_bytes()).hexdigest(),
    'running_binary_identity_verified': False,
    'provenance_note': 'Fixture/version checked over UART; local ELF hash is reference metadata, not a readback of the running firmware.',
    'complete_valid_batch': bool(valid), 'samples': len(samples),
    'raw_min': min(raw) if raw else None, 'raw_max': max(raw) if raw else None,
    'raw_mean': statistics.mean(raw) if raw else None,
    'ground_sanity_pass': bool(valid and max(raw) <= 64) if a.input_mv == 0 else None,
    'ground_sanity_limit_raw': 64 if a.input_mv == 0 else None,
    'ground_sanity_note': 'Bench smoke-test threshold, not a silicon accuracy specification',
    'records': records,
}
(a.out / 'results.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps({k: v for k, v in summary.items() if k != 'records'}, indent=2))
if not valid or summary['ground_sanity_pass'] is False: raise SystemExit(1)
