# The Pixhawk 6X's FM25V02A parameter F-RAM (the board files' peer), kept framed across the
# engine's end-of-transfer. ArduPilot's AP_RAMTRON holds chip select over two SPI transfers,
# the opcode and address, then the data. The STM32H7 SPI model ends each transfer with
# FinishTransmission, which ScriptedSpiSlave reports as a deselect although the GPIO chip
# select is still low, so the stock peer took the data phase for a new opcode: reads
# returned zeros and every parameter write was lost.
import _board_peers

_base = _board_peers.load("fm25v02a")


class Slave(_base.Slave):
    def on_deselect(self):
        if self.op in (0x02, 0x03) and self.idx == 3:
            return                     # address sent, data follows in the next transfer
        super().on_deselect()

    def on_select(self):
        if self.op in (0x02, 0x03) and self.idx == 3:
            return
        super().on_select()
