#!/bin/sh
# Builds uart_txdma.elf (bare metal, arm-none-eabi-gcc). Flash it to a
# NUCLEO-F446RE (or F401RE) and read the ST-LINK virtual COM port at 115200.
set -eu
cd "$(dirname "$0")"
arm-none-eabi-gcc -mcpu=cortex-m4 -mthumb -Os -g -ffreestanding -nostdlib \
  -Wall -Wextra -Werror -T stm32f401re.ld uart_txdma.c -o uart_txdma.elf
arm-none-eabi-objcopy -O binary uart_txdma.elf uart_txdma.bin
arm-none-eabi-size uart_txdma.elf
