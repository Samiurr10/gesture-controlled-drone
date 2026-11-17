//
// Copyright (c) 2026 Simantic
//
// This file is licensed under the MIT License.
// Full license text: LICENSE at the root of this repository (see NOTICE).
//
using Antmicro.Renode.Core;
using Antmicro.Renode.Peripherals.Bus;
using Antmicro.Renode.Peripherals.Miscellaneous;
using Antmicro.Renode.Peripherals.Wireless;

namespace Antmicro.Renode.Peripherals.RngFixed
{
    // ESP32-C3 APB_CTRL / SYSCON window (base 0x6002_6000). This block hosts both the
    // hardware-RNG entropy register (WDEV_RND_REG = 0x6002_60B0) and the WiFi/BT clock
    // gate register (SYSCON_WIFI_CLK_EN_REG = +0x014).
    //
    // WDEV_RND_REG: the 2nd-stage bootloader and IDF gather entropy by repeatedly reading
    // it and XORing successive values (bootloader_fill_random, esp_fill_random). If the
    // register reads a constant (e.g. unmapped -> 0) the gathered entropy never changes
    // and the RNG warm-up spins forever. This model returns a fresh pseudo-random 32-bit
    // value on every read so successive reads differ, which is all the warm-up requires.
    // The sequence is a fixed-seed xorshift32: DETERMINISTIC (reproducible across runs,
    // which the sim requires) -- true randomness is not needed, only that the value
    // CHANGES each read. Ported verbatim from the scripted boot model (rng.py).
    //
    // WIFI_CLK_EN (0x014): the BLE controller's esp_phy_enable asserts that the modem
    // clock gate holds PHY_INIT_MODEM_CLOCK_REQUIRED_BITS (C3 = 0x788F8F) --
    // phy_module_has_clock_bits reads this register (periph_ctrl.c). The controller's
    // enable path only ORs in WIFI_BT_COMMON (0x78078F); the remaining 0x8800 bits are
    // "modem clocks available" defaults present on running silicon. We don't model clock
    // gating dynamics, so the register reads the all-modem-clocks-enabled value
    // SYSTEM_WIFI_CLK_EN_V = 0x00FB9FCF (a superset of the required bits) and stores the
    // firmware's read-modify-write updates. Every other offset in the window keeps the
    // RNG default (random read / ignored write) so the shipped boot path is unchanged,
    // except SYSTEM_WIFI_RST_EN_REG (+0x018) below.
    //
    // SYSTEM_WIFI_RST_EN_REG (+0x018): despite the name, this is a SYSCON register, not
    // one in the SYSTEM block (soc/syscon_reg.h #defines SYSTEM_WIFI_RST_EN_REG as an
    // alias of SYSCON_WIFI_RST_EN_REG) -- a classic name-vs-location trap documented in
    // pyrite's esp32c3-wifi-register-surface.md. WIFIMAC_RST is bit2; the WiFi HAL's
    // reset sequence (periph_module_reset-style) sets it to hold the MAC in reset, then
    // clears it to release. That release edge is what (re)initializes the MAC on
    // silicon, so a 1->0 transition on bit2 here resets the WifiMac peripheral, if one
    // is wired via the WifiMac property.
    public class ESP32C3_Rng : IDoubleWordPeripheral, IKnownSize, IHasRandomSeed
    {
        public ESP32C3_Rng(IMachine machine)
        {
        }

        // Set from the .replx to cross-reference the WiFi MAC peripheral (e.g.
        // `apb_ctrl: Miscellaneous.ESP32C3_Rng @ sysbus 0x60026000` +
        // `WifiMac: wifimac`), mirroring how other repls reference peripherals by
        // name (e.g. flashdev's UnderlyingMemory). Optional: unset if no WiFi MAC
        // is present on the board.
        public ESP32C3_WifiMac WifiMac { get; set; }
        // Per-machine seed (IHasRandomSeed). xorshift32 needs a non-zero state, so
        // a zero seed keeps the default.
        public int Seed
        {
            set
            {
                seed = value == 0 ? DefaultSeed : (uint)value;
                state = seed;
            }
        }

        public long Size => 0x100;

        public void Reset()
        {
            // The stream continues across a chip reset: a hardware RNG never replays a
            // previous boot's values, so firmware that draws a per-boot ID gets a new one.
            wifiClkEn = WifiClkEnReset;
            wifiRstEn = 0;
        }

        public uint ReadDoubleWord(long offset)
        {
            if(offset == WifiClkEnOffset)
            {
                return wifiClkEn;
            }
            if(offset == WifiRstEnOffset)
            {
                return wifiRstEn;
            }
            // xorshift32; any other read in the window advances and returns the state,
            // matching the scripted model (the live consumer is WDEV_RND_REG).
            var x = state;
            x ^= x << 13;
            x ^= x >> 17;
            x ^= x << 5;
            state = x;
            return state;
        }

        public void WriteDoubleWord(long offset, uint value)
        {
            if(offset == WifiClkEnOffset)
            {
                // Store the controller's SET_/CLEAR_PERI_REG_MASK updates so they read back.
                wifiClkEn = value;
                return;
            }
            if(offset == WifiRstEnOffset)
            {
                var wasAsserted = (wifiRstEn & WifiMacRstBit) != 0;
                var isAsserted = (value & WifiMacRstBit) != 0;
                wifiRstEn = value;
                if(wasAsserted && !isAsserted)
                {
                    WifiMac?.Reset();
                }
                return;
            }
            // WDEV_RND_REG and the rest of the window are read-only/ignored.
        }

        // Arbitrary non-zero seed (matches rng.py so the value stream is identical).
        private const uint DefaultSeed = 0x2545F491;
        private uint seed = DefaultSeed;
        private uint state = DefaultSeed;

        // SYSCON_WIFI_CLK_EN_REG (offset 0x014); reset reads all modem clocks enabled
        // (SYSTEM_WIFI_CLK_EN_V), so esp_phy_enable's required-clock-bits assert passes.
        private const long WifiClkEnOffset = 0x014;
        private const uint WifiClkEnReset = 0x00FB9FCF;
        private uint wifiClkEn = WifiClkEnReset;

        // SYSCON_WIFI_RST_EN_REG (offset 0x018): FE_RST = bit1, WIFIMAC_RST = bit2.
        private const long WifiRstEnOffset = 0x018;
        private const uint WifiMacRstBit = 1u << 2;
        private uint wifiRstEn;
    }
}
