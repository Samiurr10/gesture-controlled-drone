//
// Copyright (c) 2026 Simantic
//
// This file is licensed under the MIT License.
// Full license text is available in 'licenses/MIT.txt'.
//
using System.Collections.Generic;
using System.Collections.ObjectModel;

using Antmicro.Renode.Core;
using Antmicro.Renode.Logging;
using Antmicro.Renode.Peripherals.Bus;
using Antmicro.Renode.Time;

namespace Antmicro.Renode.Peripherals.Timers
{
    // ESP32-S3 Timer Group (TIMG0 @0x6001_F000, TIMG1 @0x6002_0000). Register
    // offsets from soc/timer_group_reg.h.
    //
    // Unlike the C3/C6/P4 stub this file is ported from, the S3 driver
    // (esp_driver_gptimer) actually arms a real alarm on these timers, so this
    // model gives each group's two general-purpose timers (T0, T1) a working
    // 54-bit (22 HI + 32 LO) up/down counter and alarm:
    //   T{n}CONFIG (0x00/0x24): USE_XTAL (bit9), ALARM_EN (bit10, R/W/SC --
    //     hardware self-clears it the instant the alarm fires), DIVIDER
    //     (bits[28:13], raw 0 == divide-by-65536 per timer_ll_set_clock_prescale),
    //     AUTORELOAD (bit29), INCREASE (bit30, counts up when set), EN (bit31).
    //   T{n}LO/HI (0x04/0x08, 0x28/0x2C): read the UPDATE-latched counter value.
    //   T{n}UPDATE (0x0C/0x30): any write snapshots the live counter into LO/HI.
    //   T{n}ALARMLO/HI, T{n}LOADLO/HI (0x10/0x14.., 0x18/0x1C..): alarm target
    //     and reload value, staged across two registers like everywhere else on
    //     this SoC family.
    //   T{n}LOAD (0x20/0x44): any write reloads the counter from LOADLO/HI.
    //   INT_ENA/RAW/ST/CLR_TIMERS (0x70/0x74/0x78/0x7C): bit0 = T0, bit1 = T1.
    //
    // Each timer is a LimitTimer used as a free-running counter (Direction
    // toggled live by INCREASE, Limit pinned at the 54-bit mask so it just
    // wraps) plus a second, disposable LimitTimer that is armed for exactly the
    // number of ticks between "now" and the programmed alarm value whenever
    // ALARM_EN is written 1 -- the same elapsed-ticks-to-target approach as
    // ESP32C3_Systimer.ArmComparator, needed here because an arbitrary alarm
    // value (not just wraparound) has to fire on virtual time, paced by the
    // firmware-programmed divider and clock source (APB 80 MHz / XTAL 40 MHz),
    // never by a fitted constant.
    //
    // MODELED SIMPLIFICATION: a descending (count-down) alarm is only exact
    // when armed with the counter already above the target and no wrap in
    // between (the common down-counter case, alarm == 0); a target the counter
    // has already passed going down before arm time is treated as "one full
    // 54-bit lap away" rather than replicating the exact missed-alarm edge
    // cases ESP32C3_Systimer documents for its (unsigned, same-side) target
    // comparison.
    //
    // MWDT (ESP32-S3 TRM v1.8 chapter 13, soc/timer_group_reg.h, hal/mwdt_ll.h):
    // four stages sequenced by the shared ESP32_WatchdogStages engine, each with
    // a hold (WDTCONFIG2-5, in MWDT ticks) and an action (WDTCONFIG0 STG0..3:
    // 0 off, 1 interrupt, 2 CPU reset, 3 system reset). The tick is the APB
    // clock divided by WDT_CLK_PRESCALE (WDTCONFIG1[31:16]; "MWDT clock period =
    // 12.5 ns * TIMG_WDT_CLK_PRESCALE"). Unlike the C3 there is no
    // WDT_CONF_UPDATE_EN latch and no XTAL select on the S3, so configuration
    // takes effect on write. Every WDT register write, including the feed, is
    // ignored unless WDTWPROTECT holds 0x50D83AA1 (MWDT_LL_WKEY_VALUE).
    //   - Interrupt stages set WDT_INT_RAW (bit 2 of INT_*_TIMERS); output 2 is
    //     the level line ETS_TG{0,1}_WDT_LEVEL_INTR_SOURCE = raw & WDT_INT_ENA.
    //     ESP-IDF's task watchdog (TIMG0) and interrupt watchdog (TIMG1) both
    //     arm stage 0 = interrupt and stage 1 = system reset.
    //   - System-reset stages raise output 4, CPU-reset stages output 3; wire
    //     them to RTC_CNTL reset-reason inputs (RESET_REASON_CORE_MWDT0/1 = 7/8,
    //     CPU0_MWDT0/1 = 11/17 in esp32s3 soc/reset_reasons.h).
    //   - A CPU-reset stage only acts when WDT_PROCPU_RESET_EN or
    //     WDT_APPCPU_RESET_EN is set; wdt_hal_init() leaves both clear. Ported
    //     from the C3 silicon finding in ESP32C3_Timg, not measured on an S3.
    //   - flashBootProtection (TIMG0 only on silicon) makes WDT_FLASHBOOT_MOD_EN,
    //     set at reset, run the MWDT with stage 0 = system reset until firmware
    //     clears it. Off by default.
    // RTC calibration (RTCCALICFG/1/2) is unchanged from ESP32C3_Timg: instant-
    // ready calibration against a nominal RC_SLOW.
    public class ESP32S3_Timg : IDoubleWordPeripheral, IKnownSize, INumberedGPIOOutput
    {
        public ESP32S3_Timg(IMachine machine, bool flashBootProtection = false)
        {
            this.flashBootProtection = flashBootProtection;
            var irqs = new Dictionary<int, IGPIO>();
            timer = new TimerState[TimerCount];
            for(var idx = 0; idx < TimerCount; idx++)
            {
                var i = idx;
                var s = new TimerState
                {
                    counter = new LimitTimer(machine.ClockSource, ApbHz, this, "timer" + i,
                        limit: Mask54, direction: Direction.Ascending, enabled: false, workMode: WorkMode.Periodic),
                    alarmTimer = new LimitTimer(machine.ClockSource, ApbHz, this, "alarm" + i,
                        limit: Mask54, direction: Direction.Ascending, enabled: false, workMode: WorkMode.OneShot, eventEnabled: true),
                    divider = 1,
                    autoReload = true,
                    increase = true,
                };
                s.alarmTimer.LimitReached += () => FireAlarm(i);
                timer[idx] = s;
                irqs[idx] = new GPIO();
            }
            irqs[WdtIrqIndex] = new GPIO();
            irqs[WdtCpuResetIndex] = new GPIO();
            irqs[WdtSysResetIndex] = new GPIO();
            Connections = new ReadOnlyDictionary<int, IGPIO>(irqs);
            wdt = new ESP32_WatchdogStages(machine.ClockSource, this, "mwdt", OnWdtStageExpired);
            Reset();
        }

        public long Size => 0x100;

        // Output lines: [0]=T0, [1]=T1, [2]=WDT level IRQs -> interrupt matrix;
        // [3]=MWDT CPU reset, [4]=MWDT system reset -> RTC_CNTL reset-reason inputs.
        public IReadOnlyDictionary<int, IGPIO> Connections { get; }

        public void Reset()
        {
            regs.Clear();
            foreach(var s in timer)
            {
                s.counter.Reset();
                s.alarmTimer.Reset();
                s.useXtal = false;
                s.divider = 1;
                s.autoReload = true;
                s.increase = true;
                s.enable = false;
                s.alarmEn = false;
                s.alarmValue = 0;
                s.loadValue = 0;
                s.snapshot = 0;
                s.intRaw = false;
                s.intEna = false;
            }
            foreach(var line in Connections.Values)
            {
                line.Unset();
            }
            regs[WdtConfig0] = WdtConfig0ResetValue;
            regs[WdtConfig1] = 1u << WdtPrescaleShift;
            regs[WdtConfig2] = 26000000;
            regs[WdtConfig3] = 0x07FFFFFF;
            regs[WdtConfig4] = 0x000FFFFF;
            regs[WdtConfig5] = 0x000FFFFF;
            regs[WdtWprotect] = WdtKey;  // soc reset value: unlocked
            wdtIntRaw = false;
            wdt.Reset();
            ApplyWdtConfig();
            UpdateWdtEnable();
        }

        public uint ReadDoubleWord(long offset)
        {
            if(offset < TimerStride)
            {
                return ReadTimer(0, offset);
            }
            if(offset < 2 * TimerStride)
            {
                return ReadTimer(1, offset - TimerStride);
            }
            switch(offset)
            {
                case IntEnaTimers:
                    return Get(IntEnaTimers);
                case IntRawTimers:
                    return (uint)((timer[0].intRaw ? 1 : 0) | (timer[1].intRaw ? 2 : 0) | (wdtIntRaw ? WdtIntBit : 0));
                case IntStTimers:
                    return (uint)(((timer[0].intRaw && timer[0].intEna) ? 1 : 0) | ((timer[1].intRaw && timer[1].intEna) ? 2 : 0)
                        | (WdtIntPending ? WdtIntBit : 0));
                case IntClrTimers:
                case WdtFeed:
                    return 0;
                case RtcCaliCfg:
                {
                    var v = Get(RtcCaliCfg) & ~CaliRdy;
                    if((v & CaliStart) != 0)  // calibration launched -> instantly ready
                    {
                        v |= CaliRdy;
                    }
                    return v;
                }
                case RtcCaliCfg1:
                {
                    var caliMax = (Get(RtcCaliCfg) >> 16) & 0x7FFF;
                    if(caliMax == 0)
                    {
                        caliMax = 1;
                    }
                    var caliValue = (uint)((ulong)caliMax * XtalHz / RcSlowHz) & 0x01FFFFFF;
                    return caliValue << 7;
                }
                case RtcCaliCfg2:
                    return Get(RtcCaliCfg2) & ~1u;  // never CALI_TIMEOUT
                default:
                    return Get(offset);
            }
        }

        public void WriteDoubleWord(long offset, uint value)
        {
            if(offset < TimerStride)
            {
                WriteTimer(0, offset, value);
                return;
            }
            if(offset < 2 * TimerStride)
            {
                WriteTimer(1, offset - TimerStride, value);
                return;
            }
            switch(offset)
            {
                case IntEnaTimers:
                    Set(offset, value);
                    timer[0].intEna = (value & 1u) != 0;
                    timer[1].intEna = (value & 2u) != 0;
                    UpdateIrq(0);
                    UpdateIrq(1);
                    UpdateWdtIrq();
                    break;
                case IntClrTimers:
                    if((value & 1u) != 0)
                    {
                        timer[0].intRaw = false;
                        UpdateIrq(0);
                    }
                    if((value & 2u) != 0)
                    {
                        timer[1].intRaw = false;
                        UpdateIrq(1);
                    }
                    if((value & WdtIntBit) != 0)
                    {
                        wdtIntRaw = false;
                        UpdateWdtIrq();
                    }
                    break;
                case IntRawTimers:
                case IntStTimers:
                    break;  // read-only
                case WdtWprotect:
                    Set(offset, value);
                    break;
                case WdtConfig0:
                case WdtConfig1:
                case WdtConfig2:
                case WdtConfig3:
                case WdtConfig4:
                case WdtConfig5:
                case WdtFeed:
                    if(Get(WdtWprotect) != WdtKey)
                    {
                        this.Log(LogLevel.Debug, "MWDT write to 0x{0:X} ignored: write-protected", offset);
                        break;
                    }
                    if(offset == WdtFeed)
                    {
                        wdt.Feed();
                        break;
                    }
                    Set(offset, value);
                    ApplyWdtConfig();
                    UpdateWdtEnable();
                    break;
                default:
                    Set(offset, value);
                    break;
            }
        }

        private uint ReadTimer(int i, long localOffset)
        {
            var s = timer[i];
            switch(localOffset)
            {
                case ConfigOffset:
                    return BuildConfig(s);
                case LoOffset:
                    return (uint)(s.snapshot & 0xFFFFFFFFUL);
                case HiOffset:
                    return (uint)((s.snapshot >> 32) & 0x3FFFFF);
                case AlarmLoOffset:
                    return (uint)(s.alarmValue & 0xFFFFFFFFUL);
                case AlarmHiOffset:
                    return (uint)((s.alarmValue >> 32) & 0x3FFFFF);
                case LoadLoOffset:
                    return (uint)(s.loadValue & 0xFFFFFFFFUL);
                case LoadHiOffset:
                    return (uint)((s.loadValue >> 32) & 0x3FFFFF);
                default:
                    return 0;  // UPDATE/LOAD are write-triggered, read as 0
            }
        }

        private void WriteTimer(int i, long localOffset, uint value)
        {
            var s = timer[i];
            switch(localOffset)
            {
                case ConfigOffset:
                    ApplyConfig(i, s, value);
                    break;
                case UpdateOffset:
                    s.snapshot = s.counter.Value & Mask54;
                    break;
                case AlarmLoOffset:
                    s.alarmValue = (s.alarmValue & ~0xFFFFFFFFUL) | value;
                    break;
                case AlarmHiOffset:
                    s.alarmValue = (s.alarmValue & 0xFFFFFFFFUL) | ((ulong)(value & 0x3FFFFF) << 32);
                    break;
                case LoadLoOffset:
                    s.loadValue = (s.loadValue & ~0xFFFFFFFFUL) | value;
                    break;
                case LoadHiOffset:
                    s.loadValue = (s.loadValue & 0xFFFFFFFFUL) | ((ulong)(value & 0x3FFFFF) << 32);
                    break;
                case LoadOffset:
                    s.counter.Value = s.loadValue & Mask54;
                    break;
                default:
                    break;  // LO/HI are read-only
            }
        }

        private void ApplyConfig(int i, TimerState s, uint value)
        {
            s.useXtal = (value & (1u << 9)) != 0;
            var alarmEnNew = (value & (1u << 10)) != 0;
            s.divider = (value >> 13) & 0xFFFF;
            s.autoReload = (value & (1u << 29)) != 0;
            var increase = (value & (1u << 30)) != 0;
            var enable = (value & (1u << 31)) != 0;

            if(s.increase != increase)
            {
                s.increase = increase;
                s.counter.Direction = increase ? Direction.Ascending : Direction.Descending;
            }
            RecalcFrequency(s);

            if(s.enable != enable)
            {
                s.enable = enable;
                s.counter.Enabled = enable;
                // The alarm compares against the counter, so it pauses with it.
                s.alarmTimer.Enabled = enable && s.alarmEn;
            }

            if(alarmEnNew && !s.alarmEn)
            {
                s.alarmEn = true;
                ArmAlarm(i, s);
            }
            else if(!alarmEnNew && s.alarmEn)
            {
                s.alarmEn = false;
                s.alarmTimer.Enabled = false;
            }
        }

        private void RecalcFrequency(TimerState s)
        {
            var sourceHz = s.useXtal ? XtalHz : ApbHz;
            var effectiveDivider = s.divider == 0 ? 65536UL : s.divider;
            s.counter.Frequency = sourceHz;
            s.counter.Divider = effectiveDivider;
            s.alarmTimer.Frequency = sourceHz;
            s.alarmTimer.Divider = effectiveDivider;
        }

        // Elapsed-ticks-to-target arming, same idea as ESP32C3_Systimer.ArmComparator:
        // compute how many counter ticks separate "now" from the programmed alarm value
        // given the current count direction, then run a disposable one-shot LimitTimer for
        // exactly that many ticks at the timer's own (already-paced) frequency/divider.
        private void ArmAlarm(int i, TimerState s)
        {
            var now = s.counter.Value & Mask54;
            var target = s.alarmValue & Mask54;
            ulong delta;
            if(s.increase)
            {
                delta = (target >= now) ? (target - now) : (Mask54 + 1 - now + target);
            }
            else
            {
                delta = (now >= target) ? (now - target) : (now + (Mask54 + 1 - target));
            }

            if(delta == 0)
            {
                s.alarmTimer.Enabled = false;
                FireAlarm(i);
                return;
            }
            s.alarmTimer.Enabled = false;
            s.alarmTimer.Value = 0;
            s.alarmTimer.Limit = delta;
            s.alarmTimer.Enabled = s.enable;
        }

        private void FireAlarm(int i)
        {
            var s = timer[i];
            s.intRaw = true;
            UpdateIrq(i);
            s.alarmEn = false;  // hardware self-clears ALARM_EN the instant the alarm fires
            if(s.autoReload)
            {
                s.counter.Value = s.loadValue & Mask54;
            }
        }

        private void UpdateIrq(int i)
        {
            var s = timer[i];
            Connections[i].Set(s.intRaw && s.intEna);
        }

        private void ApplyWdtConfig()
        {
            var cfg0 = Get(WdtConfig0);
            var prescale = (Get(WdtConfig1) >> WdtPrescaleShift) & 0xFFFF;
            wdt.Frequency = ApbHz / System.Math.Max(1u, prescale);
            wdt.Hold[0] = Get(WdtConfig2);
            wdt.Hold[1] = Get(WdtConfig3);
            wdt.Hold[2] = Get(WdtConfig4);
            wdt.Hold[3] = Get(WdtConfig5);
            wdt.Action[0] = FlashBoot(cfg0) ? ActionSysReset : (cfg0 >> 29) & 3;
            wdt.Action[1] = (cfg0 >> 27) & 3;
            wdt.Action[2] = (cfg0 >> 25) & 3;
            wdt.Action[3] = (cfg0 >> 23) & 3;
        }

        private void UpdateWdtEnable()
        {
            var cfg0 = Get(WdtConfig0);
            wdt.Enabled = FlashBoot(cfg0) || (cfg0 & WdtEn) != 0;
        }

        private bool FlashBoot(uint cfg0)
        {
            return flashBootProtection && (cfg0 & WdtFlashbootModEn) != 0;
        }

        private void OnWdtStageExpired(int stage, uint action)
        {
            switch(action)
            {
                case ActionInterrupt:
                    this.Log(LogLevel.Debug, "MWDT stage {0} expired: interrupt", stage);
                    wdtIntRaw = true;
                    UpdateWdtIrq();
                    break;
                case ActionCpuReset:
                    if((Get(WdtConfig0) & (WdtProcpuResetEn | WdtAppcpuResetEn)) == 0)
                    {
                        this.Log(LogLevel.Warning, "MWDT stage {0} expired: CPU reset requested but WDT_PROCPU/APPCPU_RESET_EN=0, no effect", stage);
                        break;
                    }
                    this.Log(LogLevel.Warning, "MWDT stage {0} expired: CPU reset", stage);
                    Connections[WdtCpuResetIndex].Set(true);
                    break;
                case ActionSysReset:
                    this.Log(LogLevel.Warning, "MWDT stage {0} expired: system reset", stage);
                    Connections[WdtSysResetIndex].Set(true);
                    break;
            }
        }

        private void UpdateWdtIrq()
        {
            Connections[WdtIrqIndex].Set(WdtIntPending);
        }

        private bool WdtIntPending => wdtIntRaw && (Get(IntEnaTimers) & WdtIntBit) != 0;

        private uint BuildConfig(TimerState s)
        {
            uint v = 0;
            if(s.useXtal)
            {
                v |= 1u << 9;
            }
            if(s.alarmEn)
            {
                v |= 1u << 10;
            }
            v |= (s.divider & 0xFFFF) << 13;
            if(s.autoReload)
            {
                v |= 1u << 29;
            }
            if(s.increase)
            {
                v |= 1u << 30;
            }
            if(s.enable)
            {
                v |= 1u << 31;
            }
            return v;
        }

        private uint Get(long offset)
        {
            return regs.TryGetValue(offset, out var value) ? value : 0u;
        }

        private void Set(long offset, uint value)
        {
            regs[offset] = value;
        }

        private class TimerState
        {
            public LimitTimer counter;
            public LimitTimer alarmTimer;
            public bool useXtal;
            public uint divider;
            public bool autoReload;
            public bool increase;
            public bool enable;
            public bool alarmEn;
            public ulong alarmValue;
            public ulong loadValue;
            public ulong snapshot;
            public bool intRaw;
            public bool intEna;
        }

        private readonly TimerState[] timer;
        private readonly ESP32_WatchdogStages wdt;
        private readonly bool flashBootProtection;
        private bool wdtIntRaw;
        private readonly Dictionary<long, uint> regs = new Dictionary<long, uint>();

        private const int TimerCount = 2;
        private const int WdtIrqIndex = 2;
        private const int WdtCpuResetIndex = 3;
        private const int WdtSysResetIndex = 4;
        private const long TimerStride = 0x24;

        private const long ConfigOffset = 0x00;
        private const long LoOffset = 0x04;
        private const long HiOffset = 0x08;
        private const long UpdateOffset = 0x0C;
        private const long AlarmLoOffset = 0x10;
        private const long AlarmHiOffset = 0x14;
        private const long LoadLoOffset = 0x18;
        private const long LoadHiOffset = 0x1C;
        private const long LoadOffset = 0x20;

        private const long IntEnaTimers = 0x70;
        private const long IntRawTimers = 0x74;
        private const long IntStTimers = 0x78;
        private const long IntClrTimers = 0x7C;

        private const long WdtConfig0 = 0x48;
        private const long WdtConfig1 = 0x4C;
        private const long WdtConfig2 = 0x50;
        private const long WdtConfig3 = 0x54;
        private const long WdtConfig4 = 0x58;
        private const long WdtConfig5 = 0x5C;
        private const long WdtFeed = 0x60;
        private const long WdtWprotect = 0x64;

        // WDTCONFIG0 reset: FLASHBOOT_MOD_EN, SYS/CPU_RESET_LENGTH = 1.
        private const uint WdtConfig0ResetValue = (1u << 14) | (1u << 15) | (1u << 18);
        private const uint WdtAppcpuResetEn = 1u << 12;
        private const uint WdtProcpuResetEn = 1u << 13;
        private const uint WdtFlashbootModEn = 1u << 14;
        private const uint WdtEn = 1u << 31;
        private const int WdtPrescaleShift = 16;
        private const uint WdtKey = 0x50D83AA1;
        private const uint WdtIntBit = 1u << 2;
        private const uint ActionInterrupt = 1;
        private const uint ActionCpuReset = 2;
        private const uint ActionSysReset = 3;

        private const long RtcCaliCfg = 0x68;
        private const long RtcCaliCfg1 = 0x6C;
        private const long RtcCaliCfg2 = 0x80;

        private const uint CaliRdy = 1u << 15;
        private const uint CaliStart = 1u << 31;
        private const ulong XtalHz = 40000000;
        private const ulong RcSlowHz = 150000;
        private const ulong ApbHz = 80000000;
        private const ulong Mask54 = (1UL << 54) - 1;
    }
}
