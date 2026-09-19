# Physical nominal-supply endpoint — 2026-09-16 America/New_York

After the ground check, the user unplugged USB, removed the GPIO1-to-GND jumper,
connected GPIO1 (header 1) to the board's 3V3 supply and reconnected USB.
No multimeter was available: **the actual rail voltage was not measured**.

The identical application completed **64/64 reads**, all **raw 4095**, at ADC1
channel 0 and attenuation encoding 3. This demonstrates input response from
near-zero ground readings to a saturated reading. It is not a voltage-accuracy,
linearity or calibrated-millivolt test. The chip's characterized measurement
range is distinct from its GPIO input voltage limits.

The PR's declared ideal 1.1 V reference / 1:4 attenuation predicts raw 3071 at
exactly 3.3 V. Hardware saturates at its nominal 3V3 rail. Because the rail is
unmeasured, this is a qualitative endpoint discrepancy, not a calibrated error
measurement. It reinforces that the model's ideal analog transfer must not be
used as a qualified silicon transfer curve. Do not silently fit the model to
this single unmeasured point. Measure several intermediate voltages before
changing gain, attenuation or calibration behavior.

Current bench state: **GPIO1 connected to 3V3**, test firmware idle after the
batch. Remove this jumper before changing to firmware that could drive GPIO1
as an output. The original flash backup remains local-only.
