#!/usr/bin/env python3
"""Run the public ESP-IDF ADC application using injected model voltages.

The ideal formula assertion verifies the declared model, not silicon accuracy.
Capture UART bytes directly: SDK 0.3.1 / engine 0.5.7 read_uart duplicated fragments
in the initial full-IDF run. No result-register or firmware writes are used.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--platform', type=Path, required=True)
p.add_argument('--image', type=Path, required=True, help='ROM + flash wrapper ELF')
p.add_argument('--app-elf', type=Path, required=True, help='local reference application ELF; not loaded or verified against wrapper')
p.add_argument('--overlay', type=Path, help='namespace-only S3AdcUnderTest.dll')
p.add_argument('--out', type=Path, required=True)
p.add_argument('--voltages-uv', type=int, nargs='+', default=[0, 500000, 900000],
               help='model input levels only; values are not physical wiring guidance')
a = p.parse_args()
if any(v < 0 or v > 0xffffffff for v in a.voltages_uv):
    p.error('voltages must fit unsigned 32-bit microvolts')
a.out.mkdir(parents=True, exist_ok=False)
os.environ.setdefault('SIMANTIC_TELEMETRY', '0')
from simantic.engine import load
load()
from Antmicro.Renode.Core import EmulationManager
from Antmicro.Renode.Peripherals.Sensor import IADCExtensions
from System import Action, Byte, Int32, UInt32
from simantic import Sim

platform = a.platform.resolve()
if a.overlay:
    import clr
    from Antmicro.Renode.Utilities import TypeManager
    clr.AddReference(str(a.overlay.resolve()))
    if not TypeManager.Instance.ScanFile(str(a.overlay.resolve())):
        raise RuntimeError('overlay type scan failed')
    original = platform.read_text()
    assert original.count('Miscellaneous.ESP32S3_Sens') == 1
    platform = a.out.resolve() / 'platform.repl'
    platform.write_text(original.replace('Miscellaneous.ESP32S3_Sens', 'AdcUnderTest.ESP32S3_Sens'))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def records(data):
    result = []
    # A run step can stop mid-line. Parse only newline-terminated records;
    # complete malformed JSON still raises, and batch checks require all samples.
    for raw_line in bytes(data).split(b'\n')[:-1]:
        line = raw_line.decode('utf-8', errors='replace').rstrip('\r')
        if line.startswith('{'):
            result.append(json.loads(line))
    return result

stream = bytearray()
batches = []
with Sim(repl=platform, elf=a.image.resolve(), uart='uart0', show_logs=False) as sim:
    machine = list(EmulationManager.Instance.CurrentEmulation.Machines)[0]
    sens = machine['sysbus.sens']
    uart = machine['sysbus.uart0']
    handler = Action[Byte](lambda value: stream.append(int(value)))
    event = uart.GetType().GetEvent('CharReceived')
    event.AddEventHandler(uart, handler)
    try:
        for _ in range(12):
            sim.run_for(.25)
            if any(r.get('type') == 'ready' for r in records(stream)):
                break
        else:
            raise AssertionError('firmware did not reach ready in 3 simulated seconds')
        # Ground plus two known inputs at every channel and attenuation. Reuse
        # the unit to exercise repeated reconfiguration and changing input.
        for voltage in a.voltages_uv:
            for attenuation in range(4):
                for channel in range(10):
                    IADCExtensions.SetVoltage(sens, UInt32(voltage), Int32(channel))
                    start = len(stream)
                    sim.send_bytes(f'read {channel} {attenuation} 8\n'.encode())
                    for _ in range(8):
                        sim.run_for(.25)
                        rows = records(stream[start:])
                        if any(r.get('type') in ('end', 'error') for r in rows):
                            break
                    expected = min(4095, voltage * 4095 * (4 - attenuation) // 4400000)
                    begin = [r for r in rows if r.get('type') == 'begin']
                    end = [r for r in rows if r.get('type') == 'end']
                    samples = [r for r in rows if r.get('type') == 'sample']
                    assert len(begin) == len(end) == 1, rows
                    batch = begin[0]['batch']
                    assert begin[0]['channel'] == channel and begin[0]['attenuation'] == attenuation
                    assert end[0]['batch'] == batch and end[0]['successful'] == end[0]['requested'] == 8
                    assert len(samples) == 8 and all(
                        r['batch'] == batch and r['index'] == i and r['status'] == 0 and r['raw'] == expected
                        for i, r in enumerate(samples)), rows
                    batches.append({'channel': channel, 'attenuation': attenuation,
                                    'input_uv': voltage, 'expected_raw': expected, 'records': rows})
            print(f'PASS input {voltage} uV: 40 channel/attenuation batches', flush=True)
        summary = {
            'scope': 'Full ESP-IDF v5.5.2 public ADC API; ideal model, not analog accuracy or timing',
            'local_reference_app_elf_sha256': sha(a.app_elf), 'simulation_image_sha256': sha(a.image),
            'provenance_note': 'Only the ROM/flash wrapper is executed; reference ELF identity is not asserted to match its embedded application.',
            'platform_sha256': sha(platform),
            'model_assembly_sha256': sha(Path(str(sens.GetType().Assembly.Location))),
            'capture': 'UART0 CharReceived bytes', 'passed_batches': len(batches),
            'passed_samples': sum(len([r for r in b['records'] if r.get('type') == 'sample']) for b in batches),
            'boot_records': records(stream)[:2], 'batches': batches,
        }
        (a.out / 'results.json').write_text(json.dumps(summary, indent=2) + '\n')
    finally:
        (a.out / 'uart.txt').write_bytes(stream)
        (a.out / 'sdk-uart.txt').write_text(sim.read_uart(from_start=True))
        (a.out / 'logs.json').write_text(json.dumps(sim.logs(from_start=True)[-500:], indent=2) + '\n')
        event.RemoveEventHandler(uart, handler)
print(f'PASS {len(batches)} batches, {summary["passed_samples"]} samples')
