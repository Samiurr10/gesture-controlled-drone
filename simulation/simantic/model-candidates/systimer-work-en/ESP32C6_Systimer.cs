//
// Copyright (c) 2026 Simantic
//
// This file is licensed under the MIT License.
// Full license text is available in 'licenses/MIT.txt'.
//
using System.Collections.Generic;
using System.Collections.ObjectModel;

using Antmicro.Renode.Core;
using Antmicro.Renode.Core.Structure.Registers;
using Antmicro.Renode.Logging;
using Antmicro.Renode.Peripherals.Timers;

using Antmicro.Renode.Peripherals.Miscellaneous;
using Antmicro.Renode.Peripherals;
using Antmicro.Renode.Peripherals.Bus;

namespace Antmicro.Renode.Peripherals.SystFixed
{
    // ESP32-C6 SYSTIMER (base 0x6000_A000). Register layout is identical to the C3
    // SYSTIMER (qemu-espressif's esp32c6_systimer is a plain subclass of
    // esp32c3_systimer with no register changes) -- see
    // include/hw/timer/esp32c6_systimer.h / esp32c3_systimer.h.
    //
    // The C6 systimer is the SoC's main high-resolution time source: ESP-IDF's
    // esp_timer and the FreeRTOS tick both ride on it. A free-running UNIT0 52-bit
    // counter at 16 MHz plus three comparators (TARGET0..2) that fire an interrupt
    // when the unit count crosses the target -- one-shot (absolute target) or
    // periodic (target = count + period, reloaded each fire).
    //
    // Counter: a ComparingTimer on the machine clock source so Value tracks sim-time
    // at read time (a scripted model cannot -- no read-time clock). Each comparator is
    // a second ComparingTimer whose CompareReached sets the target's INT_RAW and, if
    // enabled, drives the matching IRQ line. IRQ 0/1/2 -> TARGET0/1/2; the C6 replx
    // wires these to the C6 interrupt controller. The FreeRTOS tick uses TARGET0 in
    // periodic mode.
    public class ESP32C6_Systimer : BasicDoubleWordPeripheral, IKnownSize, INumberedGPIOOutput
    {
        public ESP32C6_Systimer(IMachine machine) : base(machine)
        {
            // 16 MHz, 52-bit wrap. Enabled so Value advances from t=0. compare must be
            // <= limit (ComparingTimer throws otherwise); park it at the wrap point.
            unit0 = new ComparingTimer(machine.ClockSource, Frequency, this, "unit0",
                limit: Mask52, enabled: true, compare: Mask52);
            // UNIT1: the C6 has a second 52-bit counter (OP 0x08, VALUE 0x48/0x4C). The
            // FreeRTOS tick ISR reads UNIT1's counter value (counter_id=1) via the same
            // UPDATE/VALID handshake as UNIT0 -- unmodelled it spins forever on VALID inside
            // the ISR. Free-runs from t=0 at 16 MHz like UNIT0.
            unit1 = new ComparingTimer(machine.ClockSource, Frequency, this, "unit1",
                limit: Mask52, enabled: true, compare: Mask52);

            comparator = new ComparingTimer[TargetCount];
            targetHi = new uint[TargetCount];
            targetLo = new uint[TargetCount];
            period = new uint[TargetCount];
            periodMode = new bool[TargetCount];
            workEnable = new bool[TargetCount];
            intRaw = new bool[TargetCount];
            intEna = new bool[TargetCount];

            var irqs = new Dictionary<int, IGPIO>();
            for(var i = 0; i < TargetCount; i++)
            {
                var idx = i;
                comparator[i] = new ComparingTimer(machine.ClockSource, Frequency, this, "comp" + i,
                    limit: Mask52, enabled: false, eventEnabled: true, compare: Mask52);
                comparator[i].CompareReached += () => OnCompareReached(idx);
                irqs[i] = new GPIO();
            }
            Connections = new ReadOnlyDictionary<int, IGPIO>(irqs);

            DefineRegisters();
        }

        public long Size => 0x100;

        // IRQ output lines: [0-2] -> TARGET0/1/2. Wire to the interrupt matrix.
        public IReadOnlyDictionary<int, IGPIO> Connections { get; }

        public override void Reset()
        {
            base.Reset();
            foreach(var c in comparator)
            {
                c.Reset();
                c.Enabled = false;
            }
            for(var i = 0; i < TargetCount; i++)
            {
                targetHi[i] = targetLo[i] = period[i] = 0;
                periodMode[i] = workEnable[i] = intRaw[i] = intEna[i] = false;
                Connections[i].Unset();
            }
            unit0Snapshot = 0;
            unit0Valid = false;
            unit1.Reset();
            unit1.Enabled = true;
            unit1Snapshot = 0;
            unit1Valid = false;
        }

        private void OnCompareReached(int i)
        {
            intRaw[i] = true;
            UpdateIrq(i);
            if(periodMode[i] && period[i] != 0)
            {
                // Re-arm for the next period. Anchor on the previous compare (not the
                // live Value) so a periodic tick does not drift.
                comparator[i].Compare = (comparator[i].Compare + period[i]) & Mask52;
            }
        }

        private void UpdateIrq(int i)
        {
            Connections[i].Set(intRaw[i] && intEna[i]);
        }

        private void SetWorkEnable(int i, bool v)
        {
            // WORK_EN is a level enable, and CONF holds all three targets' bits: IDF
            // updates one alarm with a read-modify-write of the whole register
            // (systimer_ll_enable_alarm), rewriting the other targets' WORK_EN
            // unchanged. Only a 0 -> 1 edge (re)arms. Re-arming on every write of 1
            // restarted the periodic FreeRTOS tick from "now" each time esp_timer
            // moved its own alarm, so a 100 Hz esp_timer starved the 100 Hz tick.
            var wasEnabled = workEnable[i];
            workEnable[i] = v;
            if(v && !wasEnabled)
            {
                // The periodic FreeRTOS tick alarm is started by setting WORK_EN after its
                // period/mode are configured (no final COMP_LOAD), so arm here on enable
                // using the now-current period/target.
                ArmComparator(i);
            }
            else if(!v)
            {
                comparator[i].Enabled = false;
            }
        }

        // TRM (ESP32-S3 v1.8 11.4.2, 11.5.3): in period mode COMPx alarms at t1 + n*period,
        // t1 being the count when it starts comparing in that mode. ESP-IDF's tick
        // setup (port_systick.c) enables the alarm and only then selects PERIOD, so a
        // mode change on an enabled comparator restarts the comparison. An unchanged
        // rewrite (read-modify-write of TARGETx_CONF) does not.
        private void SetPeriodMode(int i, bool v)
        {
            var changed = periodMode[i] != v;
            periodMode[i] = v;
            if(changed && workEnable[i])
            {
                ArmComparator(i);
            }
        }

        private void ArmComparator(int i)
        {
            // Each comparator is its own ComparingTimer whose Value is independent of
            // unit0's. ComparingTimer fires after (Compare - comparator.Value) ticks, but
            // the ESP targets are expressed in unit0's frame, so align the comparator's
            // Value to unit0 before programming Compare -- otherwise the alarm fires late
            // by whatever unit0 had reached at arm time (the frame-mismatch bug).
            comparator[i].Value = unit0.Value & Mask52;
            if(periodMode[i])
            {
                comparator[i].Compare = (unit0.Value + period[i]) & Mask52;
            }
            else
            {
                var target = ((ulong)(targetHi[i] & 0xFFFFF) << 32 | targetLo[i]) & Mask52;
                // Missed-target semantics per the P4 TRM ch.15 Table 15.5-2 /
                // C3 TRM ch.10 Table 10.4-2 "Trigger Point" (same systimer
                // generation on C2/C3/C6/H2/S3, whose systimer_ll.h all
                // declare SYSTIMER_LL_ALARM_MISS_COMPENSATE for exactly this
                // reason):
                //   tc - tt <= 0            -> alarm when the counter reaches tt
                //   0 <= tc - tt < 2^51 - 1
                //   AND (tc < 2^51) == (tt < 2^51)
                //                           -> "An alarm is triggered
                //                              immediately."
                //   otherwise               -> the counter wraps and the alarm
                //                              fires when it reaches tt again.
                // The same-side-of-2^51 parenthetical is real silicon
                // behavior, not spec pedantry: verified on an ESP32-C3 bench
                // (hil-setups/c3-systimer-miss) that a target "behind" the
                // counter only by virtue of wrapping does NOT fire -- the
                // comparison is plain, not modular. Without the immediate
                // case, an alarm armed a few ticks late (Zephyr's tick driver
                // runs MIN_DELAY = 1 cycle and re-arms from its own ISR)
                // waits for the 52-bit wrap: the tick dies after one miss.
                var now = unit0.Value & Mask52;
                var sameSide = (now < (1UL << 51)) == (target < (1UL << 51));
                // tc == tt sits in both of the table's first two rows; the
                // immediate row governs (a comparator armed with Compare ==
                // Value would otherwise wait a full wrap).
                if(workEnable[i] && target <= now && now - target < (1UL << 51) - 1 && sameSide)
                {
                    comparator[i].Enabled = false;
                    OnCompareReached(i);
                    return;
                }
                comparator[i].Compare = target;
            }
            comparator[i].Enabled = workEnable[i];
        }

        private void DefineRegisters()
        {
            Registers.Conf.Define(this)
                .WithReservedBits(0, 22)
                .WithFlag(22, writeCallback: (_, v) => SetWorkEnable(2, v), valueProviderCallback: _ => workEnable[2], name: "TARGET2_WORK_EN")
                .WithFlag(23, writeCallback: (_, v) => SetWorkEnable(1, v), valueProviderCallback: _ => workEnable[1], name: "TARGET1_WORK_EN")
                .WithFlag(24, writeCallback: (_, v) => SetWorkEnable(0, v), valueProviderCallback: _ => workEnable[0], name: "TARGET0_WORK_EN")
                .WithReservedBits(25, 4)
                .WithFlag(29, name: "TIMER_UNIT1_WORK_EN")
                .WithFlag(30, name: "TIMER_UNIT0_WORK_EN")
                .WithReservedBits(31, 1);

            Registers.Unit0Op.Define(this)
                .WithReservedBits(0, 29)
                .WithFlag(29, FieldMode.Read, valueProviderCallback: _ => unit0Valid, name: "TIMER_UNIT0_VALUE_VALID")
                .WithFlag(30, FieldMode.Write, writeCallback: (_, v) => { if(v) { unit0Snapshot = unit0.Value; unit0Valid = true; } }, name: "TIMER_UNIT0_UPDATE")
                .WithReservedBits(31, 1);

            Registers.Unit0LoadHi.Define(this)
                .WithValueField(0, 20, out unit0LoadHi, name: "TIMER_UNIT0_LOAD_HI")
                .WithReservedBits(20, 12);
            Registers.Unit0LoadLo.Define(this)
                .WithValueField(0, 32, out unit0LoadLo, name: "TIMER_UNIT0_LOAD_LO");
            Registers.Unit0Load.Define(this)
                .WithFlag(0, FieldMode.Write, writeCallback: (_, v) =>
                {
                    if(v)
                    {
                        unit0.Value = ((ulong)unit0LoadHi.Value << 32 | unit0LoadLo.Value) & Mask52;
                    }
                }, name: "TIMER_UNIT0_LOAD")
                .WithReservedBits(1, 31);

            Registers.Unit0ValueHi.Define(this)
                .WithValueField(0, 20, FieldMode.Read, valueProviderCallback: _ => (uint)(unit0Snapshot >> 32), name: "TIMER_UNIT0_VALUE_HI")
                .WithReservedBits(20, 12);
            Registers.Unit0ValueLo.Define(this)
                .WithValueField(0, 32, FieldMode.Read, valueProviderCallback: _ => (uint)(unit0Snapshot & 0xFFFFFFFF), name: "TIMER_UNIT0_VALUE_LO");

            // UNIT1 -- same UPDATE/VALID snapshot + LOAD/VALUE handshake as UNIT0, one unit up.
            Registers.Unit1Op.Define(this)
                .WithReservedBits(0, 29)
                .WithFlag(29, FieldMode.Read, valueProviderCallback: _ => unit1Valid, name: "TIMER_UNIT1_VALUE_VALID")
                .WithFlag(30, FieldMode.Write, writeCallback: (_, v) => { if(v) { unit1Snapshot = unit1.Value; unit1Valid = true; } }, name: "TIMER_UNIT1_UPDATE")
                .WithReservedBits(31, 1);
            Registers.Unit1LoadHi.Define(this)
                .WithValueField(0, 20, out unit1LoadHi, name: "TIMER_UNIT1_LOAD_HI")
                .WithReservedBits(20, 12);
            Registers.Unit1LoadLo.Define(this)
                .WithValueField(0, 32, out unit1LoadLo, name: "TIMER_UNIT1_LOAD_LO");
            Registers.Unit1Load.Define(this)
                .WithFlag(0, FieldMode.Write, writeCallback: (_, v) =>
                {
                    if(v)
                    {
                        unit1.Value = ((ulong)unit1LoadHi.Value << 32 | unit1LoadLo.Value) & Mask52;
                    }
                }, name: "TIMER_UNIT1_LOAD")
                .WithReservedBits(1, 31);
            Registers.Unit1ValueHi.Define(this)
                .WithValueField(0, 20, FieldMode.Read, valueProviderCallback: _ => (uint)(unit1Snapshot >> 32), name: "TIMER_UNIT1_VALUE_HI")
                .WithReservedBits(20, 12);
            Registers.Unit1ValueLo.Define(this)
                .WithValueField(0, 32, FieldMode.Read, valueProviderCallback: _ => (uint)(unit1Snapshot & 0xFFFFFFFF), name: "TIMER_UNIT1_VALUE_LO");

            // Per-target compare registers (stride 8): TARGETi_HI/LO, TARGETi_CONF,
            // COMPi_LOAD. Target/period stage the value; COMPi_LOAD arms the comparator.
            for(var t = 0; t < TargetCount; t++)
            {
                var i = t;
                ((Registers)((long)Registers.Target0Hi + i * 8)).Define(this)
                    .WithValueField(0, 20, writeCallback: (_, v) => targetHi[i] = (uint)v, valueProviderCallback: _ => targetHi[i], name: "TARGET_HI")
                    .WithReservedBits(20, 12);
                ((Registers)((long)Registers.Target0Lo + i * 8)).Define(this)
                    .WithValueField(0, 32, writeCallback: (_, v) => targetLo[i] = (uint)v, valueProviderCallback: _ => targetLo[i], name: "TARGET_LO");
                ((Registers)((long)Registers.Target0Conf + i * 4)).Define(this)
                    .WithValueField(0, 26, writeCallback: (_, v) => period[i] = (uint)v, valueProviderCallback: _ => period[i], name: "TARGET_PERIOD")
                    .WithReservedBits(26, 4)
                    .WithFlag(30, writeCallback: (_, v) => SetPeriodMode(i, v), valueProviderCallback: _ => periodMode[i], name: "TARGET_PERIOD_MODE")
                    .WithFlag(31, name: "TARGET_TIMER_UNIT_SEL");
                ((Registers)((long)Registers.Comp0Load + i * 4)).Define(this)
                    .WithFlag(0, FieldMode.Write, writeCallback: (_, v) => { if(v) { ArmComparator(i); } }, name: "COMP_LOAD")
                    .WithReservedBits(1, 31);
            }

            Registers.IntEna.Define(this)
                .WithFlags(0, TargetCount, writeCallback: (i, _, v) => { intEna[i] = v; UpdateIrq(i); }, valueProviderCallback: (i, _) => intEna[i], name: "TARGET_INT_ENA")
                .WithReservedBits(TargetCount, 32 - TargetCount);
            Registers.IntRaw.Define(this)
                .WithFlags(0, TargetCount, FieldMode.Read, valueProviderCallback: (i, _) => intRaw[i], name: "TARGET_INT_RAW")
                .WithReservedBits(TargetCount, 32 - TargetCount);
            Registers.IntClr.Define(this)
                .WithFlags(0, TargetCount, FieldMode.Write, writeCallback: (i, _, v) => { if(v) { intRaw[i] = false; UpdateIrq(i); } }, name: "TARGET_INT_CLR")
                .WithReservedBits(TargetCount, 32 - TargetCount);
            Registers.IntStatus.Define(this)
                .WithFlags(0, TargetCount, FieldMode.Read, valueProviderCallback: (i, _) => intRaw[i] && intEna[i], name: "TARGET_INT_ST")
                .WithReservedBits(TargetCount, 32 - TargetCount);
        }

        private ulong unit0Snapshot;
        private bool unit0Valid;
        private IValueRegisterField unit0LoadHi;
        private IValueRegisterField unit0LoadLo;
        private ulong unit1Snapshot;
        private bool unit1Valid;
        private IValueRegisterField unit1LoadHi;
        private IValueRegisterField unit1LoadLo;
        private readonly ComparingTimer unit0;
        private readonly ComparingTimer unit1;
        private readonly ComparingTimer[] comparator;
        private readonly uint[] targetHi;
        private readonly uint[] targetLo;
        private readonly uint[] period;
        private readonly bool[] periodMode;
        private readonly bool[] workEnable;
        private readonly bool[] intRaw;
        private readonly bool[] intEna;

        private const int TargetCount = 3;
        private const ulong Frequency = 16000000;
        private const ulong Mask52 = (1UL << 52) - 1;

        private enum Registers : long
        {
            Conf         = 0x0000,
            Unit0Op      = 0x0004,
            Unit1Op      = 0x0008,
            Unit0LoadHi  = 0x000C,
            Unit0LoadLo  = 0x0010,
            Unit1LoadHi  = 0x0014,
            Unit1LoadLo  = 0x0018,
            Target0Hi    = 0x001C,
            Target0Lo    = 0x0020,
            Target0Conf  = 0x0034,
            Unit0ValueHi = 0x0040,
            Unit0ValueLo = 0x0044,
            Unit1ValueHi = 0x0048,
            Unit1ValueLo = 0x004C,
            Comp0Load    = 0x0050,
            Unit0Load    = 0x005C,
            Unit1Load    = 0x0060,
            IntEna       = 0x0064,
            IntRaw       = 0x0068,
            IntClr       = 0x006C,
            IntStatus    = 0x0070,
        }
    }
}
