#!/usr/bin/env python3
"""Runs uart_txdma.elf on the STM32F446RE model, stock or with the STM32_UART
candidate (PALMPILOT_STM32_UART_OVERLAY; empty = stock). Exits 0 on RESULT: PASS.

    python3 firmware/tools/palmpilot.py env >/dev/null; .venv-simantic/bin/python firmware/probes/stm32-uart-txdma/run.py
"""
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "firmware/tools"))
os.environ.setdefault("SIMANTIC_TELEMETRY", "0")
from simantic.engine import load  # noqa: E402
load()
from Antmicro.Renode.Core import EmulationManager  # noqa: E402
from System import Action, Byte  # noqa: E402
from simantic import Sim  # noqa: E402
from harness import accept_repl_files, load_overlay  # noqa: E402

text = (ROOT / "tmp/simantic/platform/STM32F446RE-0.5.20.repl").read_text()
text += (HERE / "usart2-txdma.repl-frag").read_text()
overlay = os.environ.get("PALMPILOT_STM32_UART_OVERLAY")
if overlay:
    load_overlay(overlay, "STM32 UART")
    text = text.replace("UART.STM32_UART", "UartFixed.STM32_UART")
repl = ROOT / "tmp/palmpilot/stm32-uart-txdma.repl"
repl.parent.mkdir(parents=True, exist_ok=True)
repl.write_text(text)

out = bytearray()
accept_repl_files()
with Sim(scenario={"machines": {"m": {"mcu": str(repl), "elf": str(HERE / "uart_txdma.elf")}}},
         machine="m", uart="usart2") as sim:
    machine = list(EmulationManager.Instance.CurrentEmulation.Machines)[0]
    uart = machine["sysbus.usart2"]
    uart.GetType().GetEvent("CharReceived").AddEventHandler(uart, Action[Byte](lambda b: out.append(int(b))))
    sim.run_for(3.0)
text = out.decode(errors="replace")
print(text.strip())
print(f"\nSTM32_UART: {'candidate' if overlay else 'stock'}")
result = re.search(r"RESULT: (\w+)", text)
sys.exit(0 if result and result.group(1) == "PASS" else 1)
