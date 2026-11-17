# The board's DPS310, reading quad_plant's altitude. A few pascals of
# deterministic jitter, as a real sensor has: AP_Baro treats a pressure that
# never changes as a stuck sensor.
import math

import _board_peers
import quad_plant

_base = _board_peers.load("dps310")
JITTER_PA = 2.0


class Slave(_base.Slave):
    def on_timer(self):
        self.jitter_phase = getattr(self, "jitter_phase", 0) + 1
        self.pressure_pa = quad_plant.PLANT.pressure_pa() + JITTER_PA * math.sin(self.jitter_phase * 2.399)
        super().on_timer()
