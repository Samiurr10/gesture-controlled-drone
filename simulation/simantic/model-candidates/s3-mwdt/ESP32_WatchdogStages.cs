//
// Copyright (c) 2026 Simantic
//
// This file is licensed under the MIT License.
// Full license text is available in 'licenses/MIT.txt'.
//
using System;

using Antmicro.Renode.Core;
using Antmicro.Renode.Peripherals.Timers;
using Antmicro.Renode.Time;

namespace Antmicro.Renode.Peripherals.Timers
{
    // Four-stage watchdog engine shared by the ESP32-C3 MWDT (TIMG) and RWDT
    // (RTC_CNTL). ESP32-C3 TRM v1.4 §12.2: the counter runs from stage 0; when
    // it reaches STGn_HOLD the stage's action fires and the counter restarts
    // for stage n+1 (wrapping to stage 0 after stage 3). A feed returns to
    // stage 0. Actions 0=off, 1=interrupt, 2=CPU reset, 3=system reset,
    // 4=RTC reset (RWDT only) — decoding of the action is the owner's job via
    // the callback; the engine only sequences the stages.
    public sealed class ESP32_WatchdogStages
    {
        public ESP32_WatchdogStages(IClockSource clockSource, IPeripheral owner, string name, Action<int, uint> onStageExpired)
        {
            this.onStageExpired = onStageExpired;
            timer = new LimitTimer(clockSource, 1, owner, name, limit: 1, direction: Direction.Ascending,
                workMode: WorkMode.OneShot, eventEnabled: true);
            timer.LimitReached += OnLimitReached;
        }

        public readonly ulong[] Hold = new ulong[4];
        public readonly uint[] Action = new uint[4];

        public ulong Frequency
        {
            get => timer.Frequency;
            set => timer.Frequency = Math.Max(1, value);
        }

        public bool Enabled
        {
            get => timer.Enabled;
            set
            {
                if(value && !timer.Enabled)
                {
                    Restart(0);
                }
                else if(!value)
                {
                    timer.Enabled = false;
                }
            }
        }

        public int Stage { get; private set; }

        public void Feed()
        {
            if(timer.Enabled)
            {
                Restart(0);
            }
        }

        public void Reset()
        {
            timer.Enabled = false;
            Stage = 0;
        }

        private void Restart(int stage)
        {
            Stage = stage;
            timer.Enabled = false;
            timer.Limit = Math.Max(1, Hold[stage]);
            timer.Value = 0;
            timer.Enabled = true;
        }

        private void OnLimitReached()
        {
            var stage = Stage;
            onStageExpired(stage, Action[stage]);
            // Reset actions tear the digital domain down (the owner resets the
            // machine, which calls Reset() here); only off/interrupt stages advance.
            if(Action[stage] < 2)
            {
                Restart((stage + 1) & 3);
            }
        }

        private readonly LimitTimer timer;
        private readonly Action<int, uint> onStageExpired;
    }
}
