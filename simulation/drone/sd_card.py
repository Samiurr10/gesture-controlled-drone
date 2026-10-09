# The board's microSD card, kept reachable so a harness can save the card image
# (ArduPilot's dataflash logs) after a run: quad_plant.SD_CARD.save(path).
import _matek_peers
import quad_plant

_base = _matek_peers.load("sd_spi")


class Slave(_base.Slave):
    def __init__(self, ctx):
        super().__init__(ctx)
        quad_plant.SD_CARD = self

    def save(self, path):
        with open(path, "wb") as f:
            f.truncate(_base.CAPACITY_BLOCKS * 512)
            for n, data in self.blocks.items():
                f.seek(n * 512)
                f.write(data)
