# BLE and host-transport capability audit

> **Report snapshot:** this documentation package includes audit reports and concise results. Test sources, setup scripts and detailed traces referenced below remain local bench material; reproduction commands require that separate harness and are not runnable from this documentation checkout alone.

Audited September 16, 2026 with **CLI/engine 0.5.7 and Python SDK 0.3.1**.
These are transport capability tests, not controller application qualification.
The hand-sensor inputs, two-hand protocol and host-to-drone bridge still need
their own implementation and acceptance tests.

## Results

| Capability | Observed result | Coverage limit |
|---|---|---|
| One nRF52840 Zephyr BLE link | **PASS:** both nodes initialized Bluetooth, connected, subscribed, and delivered a GATT heart-rate notification by 1.5 virtual seconds; 149 radio frames recorded | Official Zephyr 2.6 demo, not Adafruit/SoftDevice or our controller packet format |
| Three nRF52840 machines | **PARTIAL:** all three initialized Bluetooth with distinct addresses; central connected to one peripheral and received seven notifications in eight virtual seconds; 911 frames recorded | Official `central_hr` selects one peer. Two simultaneous links remain **not established by this fixture**, not an observed simulator incapability |
| CLI UART-to-TCP bridge | **PASS:** host received Zephyr shell prompt, sent `demo ping`, and received `pong`; five-second run exited successfully | UART0 using an explicit legacy-UART platform variant; wall-clock socket test, not USB |
| nRF USB supply/ready handling | **PASS:** `POWER.USBREGSTATUS=3`; USBD enable raised READY and USBEVENT; acknowledgements cleared both | Direct model-register transactions, not a compiled USB stack |
| nRF USB device-to-host IN2 | **PARTIAL:** exact `PALMPILOT_USB_IN_PROBE\n` payload reached host and ENDEPIN2 fired | `EPIN[2].AMOUNT` stayed zero and emitted an unhandled-register warning, rather than reporting the 23-byte transfer |
| nRF USB host-to-device bulk OUT | **BLOCKED:** `ConnectEndpointWrite(1..7)` returned null after enabling OUT1/OUT2 | No bulk OUT host pipe available through this runtime model; EP0 setup pipe exists |
| CLI `--usb-cdc-console usbd` | Attachment command accepted and ran for two virtual seconds | Input ELF was UART-only; this does **not** prove USB enumeration or CDC transfer |
| Adafruit core / S140 SoftDevice / TinyUSB | **NOT TESTED** | No matching combined application/stack fixture was available in this audit |

Read [results.json](results.json) for individual assertions, version/hash records,
UART output and aggregated model warnings. The local bench evidence directory retains timestamped BLE frames, initial BLE UART records and CLI traces. The
recorded BLE success includes model warnings about unsupported radio fields;
it is a bounded functional result, not complete register conformance.

The first two-node fixture uses the catalog's default factory identity on both
machines. The three-node run corrects this explicitly with distinct FICR
`DEVICEADDR[0:1]` read hooks: central `C0:DE:AA:BB:CC:D1`, left `...:D2`, right
`...:D3`. The actual runtime FICR model exposes no identity property. The read
hook is test configuration and is recorded in the script; it does not replace
the radio or Bluetooth stack.

## Reproduce

From the repository root, use the already-configured `.venv-simantic` and engine
installation. These scripts do not update Simantic or ask for account secrets.

```sh
.venv-simantic/bin/python simulation/simantic/capability-audit/transport/fetch_fixtures.py
export SIMANTIC_HOME="$PWD/tmp/simantic/runtime"
export SIMANTIC_TELEMETRY=0
.venv-simantic/bin/python simulation/simantic/capability-audit/transport/audit_ble.py
.venv-simantic/bin/python simulation/simantic/capability-audit/transport/audit_ble_three_nodes.py
.venv-simantic/bin/python simulation/simantic/capability-audit/transport/audit_uart_tcp.py
```

The TCP test also needs `tmp/simantic/models/NRF52840QIAA.repl`, the captured
catalog platform. It creates a temporary variant with `easyDMA: false` for the
official legacy-UART fixture, as its upstream test requires. BLE tests use the
catalog model unchanged, apart from the explicit three-node identity hooks.

For the USB register audit, first build the sibling
SDK I/O scaffold (`../sdk/build.py`, local bench), then run:

```sh
.venv-simantic/bin/python simulation/simantic/capability-audit/sdk/build.py
.venv-simantic/bin/python simulation/simantic/capability-audit/transport/audit_usb_registers.py
```

The USB audit intentionally returns nonzero for the observed AMOUNT assertion
failure. Its CPU scaffold does not initialize USB: the Python script explicitly
exercises the model's registers and host pipes while virtual time is held. This
isolates peripheral behavior; it is not a USB firmware-driver test.

New outputs go to `tmp/simantic/audit/transport/`. The tracked results are the
reviewed audit snapshot and are not silently rewritten on reruns. In this
environment, simulator execution required access to Renode's normal per-user
configuration lock; the initial sandboxed attempt did not start the model.

## Next capability work

1. Supply a versioned BLE central fixture supporting at least two concurrent
   connections and unique peripheral identities. Verify independent
   notifications from both peers at the same time, then loss/reconnect.
2. Test the actual selected Adafruit core/S140 combination before choosing it
   as the controller simulation stack. A standalone SoftDevice image cannot
   establish application/stack compatibility.
3. Resolve USB bulk OUT host-pipe support and `EPIN[n].AMOUNT`; then test full
   enumeration, descriptors, configuration, CDC class requests and bidirectional
   packets using the selected USB firmware stack. Current READY handling works.
4. UART-over-TCP can support an explicitly labeled simulator-only command
   adapter while USB work proceeds. It does not qualify the physical Feather
   USB connection, and the command schema/expiry/bridge remain project work.

## Fixture and source provenance

The [fixture lock](fixture-lock.json) records each official download URL, size,
published SHA-1 and independently recorded SHA-256. The downloader requires the
recorded SHA-256 before any fixture is used. Large downloaded ELFs remain in
the ignored temporary directory.

- [Official BLE scenario at audited Simantic upstream revision](https://github.com/simantic-dev/renode-upstream/blob/613ff62434dc94a5725b2363f2e0558b25e22b08/scripts/multi-node/nrf52840-ble-zephyr.resc).
- [Official nRF52840 regression expectations and legacy UART configuration](https://github.com/simantic-dev/renode-upstream/blob/613ff62434dc94a5725b2363f2e0558b25e22b08/tests/platforms/NRF52840.robot).
- [Nordic nRF52840 register definitions](https://github.com/NordicSemiconductor/nrfx/blob/v3.14.0/mdk/nrf52840.h): USBD base `0x40027000`, POWER/USB readiness and endpoint DMA register layout.
- [Public USB model source inspected](https://github.com/simantic-dev/renode-infrastructure-upstream/blob/a0fcf54f9a31591e607e75143b796aeb4da626b8/src/Emulator/Peripherals/Peripherals/USB/NRF_USBD.cs). The installed 0.5.7 model is newer/different; conclusions above come from the runtime probes, not this source's missing behavior.
