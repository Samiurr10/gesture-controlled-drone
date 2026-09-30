//
// Copyright (c) 2026 Simantic
//
// This file is licensed under the MIT License.
// Full license text is available in 'licenses/MIT.txt'.
//
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;

using Antmicro.Renode.Core;
using Antmicro.Renode.Core.Structure.Registers;
using Antmicro.Renode.Exceptions;
using Antmicro.Renode.Logging;
using Antmicro.Renode.Peripherals.Bus;
using Antmicro.Renode.Peripherals.Wireless;
using Antmicro.Renode.Time;
using Antmicro.Renode.Utilities.Crypto;

namespace Antmicro.Renode.Peripherals.BleFixed
{
    // ESP32-C3 BLE controller — the CEVA RivieraWaves RW-BLE v9 link-layer core, the
    // SAME IP as the ESP32-S3 (verified: both ship in ESP-IDF's single
    // `lib_esp32c3_family/` blob dir; 892 RW symbols 100% shared) and the same RW9 core
    // as onsemi RSL10 (RSLxx_Radio.cs). So this model mirrors RSLxx_Radio's structure;
    // only the register BASE and a few offsets differ (Espressif splits the core across
    // two MMIO windows instead of RSL10's single 0x40001500 block):
    //
    //   0x60031000  LL-MAC core  — RW-BLE control/version/interrupt/time cluster
    //                              (this peripheral). The "reg_blecore.h" equivalent.
    //   0x60011000  BT/MAC       — hw enable/sleep/wake + a BT-local interrupt
    //                              controller (0x6001186c). Modelled separately once
    //                              the init fault-loop shows the controller needs it.
    //
    // The register map for these blocks is NOT in the C3 TRM (Espressif ships the
    // controller as libbtdm_app.a with no public spec). What IS decoded here comes from
    // two grounded sources, same method as docs/esp32s3-ble-register-decode.md:
    //   1. disassembling the C3 blob (riscv32-esp-elf-objdump libbtdm_app.a), and
    //   2. the S3 silicon trace (which == C3), docs/esp32s3-ble-register-decode.md.
    //
    // Milestone state (see docs/esp32c3-ble-m3-continuous-scan.md):
    //   M1 — boot: register core so controller init runs without faulting and reaches
    //        HCI-reset-complete (BaseTimeCount clock capture is the one decoded init poll).
    //   M2 — advertising: the LL transmits ADV_IND onto BLEMedium each interval (adv ticker).
    //   M3 groundwork (LANDED): the interrupt-priority-dispatch register (0x2D8
    //        InterruptPriority) that unblocks ALL RWBLE interrupt servicing, the fine/coarse
    //        event-anchor comparator (ArmEventTimer/OnEventTimer), and the RX descriptor/
    //        Exchange-Memory contract (FillRxDescriptor/ResolveEmOffset).
    //        Continuous-scan engine (LANDED, not yet reaching 043e): a tracked scan-event
    //        window (OpenScanWindow/CloseScanWindow/IsRxGateOpen) reads the firmware's own
    //        sch_prog state instead of injecting synthetic RX/END, and ArmEventTimer no longer
    //        re-schedules on an unchanged already-armed target (the §3.4 re-program-storm
    //        guard). Bounded two-node run stays clean (no assert, no storm) but the sch_prog
    //        slot/EM-segment addresses this reads are not yet live-verified against this
    //        firmware build, so the RX gate never opens for real. See
    //        docs/esp32c3-ble-m3-continuous-scan.md for what remains.
    public class ESP32C3_Radio : BasicDoubleWordPeripheral, IRadioWithReceptionStatus, IRadioWithTransmitPhy, IHasClockScale, IKnownSize, INumberedGPIOOutput, IGPIOReceiver
    {
        // emBaseRegLut: ROM address of em_base_reg_lut, the table r_emi_get_mem_addr_by_offset
        // walks to turn an Exchange-Memory offset into a mapping-register index + region base.
        // Same table contents and entry layout on the C3 and S3 ROMs, different address:
        // esp32c3_rev3_rom.elf 0x3ff1f518 (default), esp32s3_rev0_rom.elf 0x3ff1f526.
        //
        // The four parameters below are the other ROM-resident data pointers this model reads
        // at runtime; the C3 and S3 ROMs place the same symbols at different addresses:
        //   lldEnvPointer  = ROM p_lld_env         c3 0x3fcdff9c, s3 0x3fceff78
        //   modulesFuncsP  = ROM r_modules_funcs_p c3 0x3fcdff88, s3 0x3fceff64
        //   lldConEnv      = ROM lld_con_env       c3 0x3fcdfc9c, s3 0x3fcefc88
        //   lldInitEnv     = ROM lld_init_env      c3 0x3fcdffb4, s3 0x3fceff90
        //   coRateToPhy    = ROM co_rate_to_phy    c3 0x3ff1f6b0, s3 0x3ff1f6c0
        public ESP32C3_Radio(IMachine machine, ulong emBaseRegLut = 0x3ff1f518,
            ulong lldEnvPointer = 0x3fcdff9c, ulong modulesFuncsP = 0x3fcdff88,
            ulong lldConEnv = 0x3fcdfc9c, ulong lldInitEnv = 0x3fcdffb4,
            ulong coRateToPhy = 0x3ff1f6b0) : base(machine)
        {
            this.emBaseRegLut = emBaseRegLut;
            this.lldEnvPointer = lldEnvPointer;
            this.modulesFuncsP = modulesFuncsP;
            this.lldConEnv = lldConEnv;
            this.lldInitEnv = lldInitEnv;
            this.coRateToPhy = coRateToPhy;
            rxBuffer = new ConcurrentQueue<KeyValuePair<byte[], IRadio>>();

            // One output line per BLE interrupt-matrix source, wired in the .repl to the
            // ESP32C3_IntMatrix at the ETS_*_SOURCE numbers (soc/interrupts.h):
            //   [0]=RWBLE(8, main LL) [1]=RWBT(7) [2]=BT_MAC(4) [3]=BT_BB(5).
            var lines = new Dictionary<int, IGPIO>();
            for(var i = 0; i < InterruptLineCount; i++)
            {
                lines[i] = new GPIO();
            }
            Connections = new ReadOnlyDictionary<int, IGPIO>(lines);

            DefineRegisters();
            Reset();
        }

        // Fault-loop trace hook: appends model-event lines to $C3BLE_TRACE when set.
        // No-op (and zero-cost gate) in normal runs.
        private void M5Trace(string msg)
        {
            if(tracePath == null)
            {
                return;
            }
            try
            {
                System.IO.File.AppendAllText(tracePath,
                    $"[{machine.LocalTimeSource.ElapsedVirtualTime.TotalMicroseconds:F0}us r{GetHashCode():X8}] {msg}\n");
            }
            catch
            {
                // tracing must never affect the run
            }
        }
        private static readonly string tracePath = Environment.GetEnvironmentVariable("C3BLE_TRACE");

        public override void Reset()
        {
            base.Reset();
            windowStorage.Clear();
            rawStatus = 0;
            interruptMask = 0;
            intPrioStored = 0;
            timeBaseMicroseconds = 0;
            eventTargetSlot = 0;
            fineTarget = 0;
            fineTargetSub = 0;
            coarseTarget = 0;
            grossTarget = 0;
            timerEpoch.Clear();
            currentChannel = AdvChannel37;
            connRole = ConnRole.None;
            connSlotDeferralHalfUs = 0;
            connAccessAddress = AdvAccessAddress;
            connActivityTag = 0;
            pendingTxDesc = 0;
            txCipherDesc = 0;
            txCipherPayload = null;
            connCryptCsTraced = 0;
            radioEventLive = false;
            radioEventSlot = 0;
            radioEventCtrlAddr = 0;
            radioEventSeg0Base = 0;
            radioEventEpoch = 0;
            radioEventScheduled = false;
            pendingRadioEvents.Clear();
            while(rxBuffer.TryDequeue(out var _)) { }
            foreach(var line in Connections.Values)
            {
                line.Unset();
            }
        }

        // The RW-BLE core is overwhelmingly plain RW configuration registers that must
        // read back. Crucially the controller's Exchange-Memory mapping registers
        // (0x60031204..0x6003129c, plus the enable bitmaps at 0x600312c4/0x600312c8/
        // 0x60031300) are PROGRAMMED at init by r_emi_em_base_init (libbtdm_app.a): it
        // malloc's the EM segments in DRAM (0x3fc80000+) and writes (ptr>>2)&0x3FFFF to
        // each mapping register. The ROM's r_emi_get_mem_addr_by_offset then reconstructs
        // the physical EM address as 0x3fc00000 | ((reg<<2)&0xFFFFC) + offset. If these
        // writes are dropped the registers read 0, the EM pins to the read-only
        // 0x3fc00000 (PMP entry 3 makes [0x3C000000,0x3fc80000) R-only, tlib enforces it),
        // and r_rf_em_init's coefficient memcpy takes a store-access fault. So any offset
        // the behavioural register map does not claim is backed by plain storage here,
        // exactly like RSLxx_Radio's StorageBackedRegisters (just window-wide rather than
        // enumerated, since the full C3 register list is not yet mapped). Undefined reads
        // still surface at Debug for the fault-loop.
        public override uint ReadDoubleWord(long offset)
        {
            if(RegistersCollection.TryRead(offset, out var value))
            {
                return value;
            }
            if(windowStorage.TryGetValue(offset, out var stored))
            {
                return stored;
            }
            this.DebugLog("Unhandled read from radio window offset 0x{0:X} (returns 0)", offset);
            return 0;
        }

        public override void WriteDoubleWord(long offset, uint value)
        {
            if(RegistersCollection.TryWrite(offset, value))
            {
                return;
            }
            this.DebugLog("Storage write to radio window offset 0x{0:X} = 0x{1:X}", offset, value);
            M5Trace($"W 0x{offset:X} = 0x{value:X}");
            windowStorage[offset] = value;
        }

        public long Size => 0x400;

        public IReadOnlyDictionary<int, IGPIO> Connections { get; }

        public event Action<IRadio, byte[]> FrameSent;

        // --- IRadio / BLEMedium contract ---------------------------------------
        public int Channel
        {
            get => currentChannel;
            set => throw new RecoverableException("Setting channel manually is not supported");
        }

        // The medium delivers a frame at its first bit; the RW-BLE core reports it (RX done,
        // descriptor, CRC/MIC verdict, NESN) after its last. A reception is therefore held
        // until its end, and a frame damaged in between completes as a CRC failure.
        public void ReceiveFrame(byte[] frame, IRadio sender, TimeStamp transmitStart)
        {
            BeginReception(frame, sender, ToLocalHalfMicroseconds(transmitStart.TimeElapsed));
        }

        public void ReceiveFrame(byte[] frame, IRadio sender)
        {
            BeginReception(frame, sender, NowHalfMicroseconds());
        }

        public void CorruptReception(IRadio sender, TimeStamp transmitStart, string reason)
        {
            var startHalfUs = ToLocalHalfMicroseconds(transmitStart.TimeElapsed);
            foreach(var reception in receptionsInFlight)
            {
                if(reception.Sender == sender && reception.StartHalfUs == startHalfUs)
                {
                    reception.CrcError = true;
                    M5Trace($"rx damaged: {reason}");
                }
            }
        }

        private void BeginReception(byte[] frame, IRadio sender, ulong startHalfUs)
        {
            if(frame.Length < AccessAddressLength + 2 || !radioEventLive)
            {
                // Too short to carry a PDU, or the radio is off: nothing to hold.
                CompleteReception(new Reception { Frame = frame, Sender = sender, StartHalfUs = startHalfUs });
                return;
            }
            var pduLength = frame.Length - AccessAddressLength;
            var endHalfUs = startHalfUs + AirTimeMicroseconds(new byte[pduLength], ActivePhyRate) * 2;
            var reception = new Reception { Frame = frame, Sender = sender, StartHalfUs = startHalfUs, EndHalfUs = endHalfUs };
            receptionsInFlight.Add(reception);
            rxInFlightUntilHalfUs = Math.Max(rxInFlightUntilHalfUs, endHalfUs);
            var nowHalfUs = NowHalfMicroseconds();
            var ts = machine.LocalTimeSource;
            var when = LocalDelay(endHalfUs > nowHalfUs ? endHalfUs - nowHalfUs : 0);
            ts.ExecuteInSyncedState(_ =>
            {
                receptionsInFlight.Remove(reception);
                CompleteReception(reception);
            }, when);
        }

        private void CompleteReception(Reception reception)
        {
            receiveTransmitStartHalfUs = reception.StartHalfUs;
            try
            {
                if(reception.CrcError)
                {
                    ReceiveDamagedFrame(reception.Frame);
                }
                else
                {
                    ReceiveFrameAtEnd(reception.Frame, reception.Sender);
                }
            }
            finally
            {
                receiveTransmitStartHalfUs = null;
            }
        }

        // A packet whose CRC failed. Advertising channels: dropped (MODELED SIMPLIFICATION:
        // the core can pass errored packets up when ADVERTFILT_EN is clear; the LL drops
        // them anyway). Connection events: reported with status bit 3, on which
        // r_lld_con_rx re-syncs the anchor and skips the rest (no ack, no supervision
        // reset). The peripheral answers with a NAK; two errors in a row close the event
        // (Core Vol 6 Part B §4.5.6). MODELED SIMPLIFICATION: the central closes after one.
        private void ReceiveDamagedFrame(byte[] frame)
        {
            frame = frame.Skip(AccessAddressLength).ToArray();
            if(!IsConnectionEventSlot(radioEventCtrlAddr, out _)
                || !IsRxGateOpen() || !TryResolveArmedControlStructure(out _, out var rxActId))
            {
                M5Trace($"rx CRC error discarded (type={frame[0] & 0xF} len={frame.Length})");
                return;
            }
            consecutiveCrcErrors++;
            var rxCtrl = sysbus.ReadWord(radioEventCtrlAddr);
            sysbus.WriteWord(radioEventCtrlAddr, (ushort)((rxCtrl & ~SchProgTypeMask) | (2 << 3)));
            FillRxDescriptor(frame, rxActId, micError: false, crcError: true);
            RaiseStatusBit(RxDoneBit);
            M5Trace($"conn data CRC error reported ({consecutiveCrcErrors} in a row)");
            if(connRole == ConnRole.Slave && consecutiveCrcErrors < 2)
            {
                ScheduleConnFrameSend(BuildConnTxPdu(), TifsAfter(frame));
            }
        }

        private void ReceiveFrameAtEnd(byte[] frame, IRadio sender)
        {
            // BLEMedium frames are access-address-prefixed (see BLEMedium's contract note);
            // everything below works on the channel PDU, so strip the AA first. Getting
            // this wrong is silent and total: with the prefix left on, frame[0] is the low
            // AA byte (0xD6 -> "type 6", never ADV_IND) and FillRxDescriptor lands AdvA
            // four bytes off, so the ROM builds no advertising report at all and the host
            // scan just reports zero devices.
            if(frame.Length < AccessAddressLength + 2)
            {
                this.WarningLog("Dropping {0}-byte medium frame: too short to carry an access address and PDU header", frame.Length);
                return;
            }
            var accessAddress = BitConverter.ToUInt32(frame, 0);
            frame = frame.Skip(AccessAddressLength).ToArray();

            M5Trace($"rx type={frame[0] & 0xF} len={frame.Length} evtLive={radioEventLive} gate={IsRxGateOpen()}");
            // Whether this is a connection-event data PDU or an adv-channel PDU is
            // decided by the event that is receiving it, not by whether this node has
            // ever held a link: the two use different physical channels and the
            // scheduler says which one is running. Keying it off connRole -- which is
            // set when a link comes up and never cleared -- routed every advertising
            // PDU into the connection path once the node had been a slave, so a
            // peripheral could not accept a CONNECT_IND after a disconnect, and a
            // second central's CONNECT_IND was decoded as connection data (LL
            // lld_adv.c:2328).
            if(IsConnectionEventSlot(radioEventCtrlAddr, out _))

            {
                // The correlator only syncs on the armed link's access address.
                if(TryResolveArmedControlStructure(out var linkCs, out _)
                    && accessAddress != sysbus.ReadDoubleWord(linkCs + CsAccessAddressOffset))
                {
                    M5Trace($"rx for another link ignored (aa=0x{accessAddress:X8})");
                    return;
                }
                HandleConnData(frame);
                return;
            }
            // M4c: SCAN_REQ never reaches the LL as an RX descriptor — real RW HW consumes
            // it and answers with the SCAN_RSP descriptor itself (silicon-verified report
            // mix, M3 doc §9). Handle it model-side on the advertiser.
            if(frame.Length >= 14 && (frame[0] & 0xF) == ScanReqPduType)
            {
                HandleScanRequest(frame);
                return;
            }
            // M3 continuous-scan engine (docs/esp32c3-ble-m3-continuous-scan.md §4): only
            // deliver into the RX descriptor while a scan-event window is open AND the sch_prog
            // EM seg-0 control for the tracked slot shows the RX gate set (bits 4/5, "type>=2")
            // -- this is the same gate r_sch_prog_rx_isr itself checks (sch_prog.c:201). Outside
            // a live window we just queue; raising RX-done asynchronously asserts the controller.
            if(IsRxGateOpen())
            {
                TryResolveArmedControlStructure(out var rxCs, out var rxActId);
                // An initiator answers only the peer the LL named in the init CS.
                if((frame[0] & 0xF) == AdvIndPduType && !IsInitiatorTarget(frame, rxCs))
                {
                    M5Trace("ADV_IND from a device the initiator is not connecting to ignored");
                    return;
                }
                FillRxDescriptor(frame, rxActId);
                // Advance the armed slot's STATE 0 -> 2 ("frame in progress") before raising
                // RX-done: ROM r_sch_prog_rx_isr (0x40030824) asserts sch_prog.c:201 unless
                // (ctrl>>3)&6 != 0 — on silicon the HW advances this as the event starts.
                var rxCtrl = sysbus.ReadWord(radioEventCtrlAddr);
                sysbus.WriteWord(radioEventCtrlAddr, (ushort)((rxCtrl & ~SchProgTypeMask) | (2 << 3)));
                RaiseStatusBit(RxDoneBit);
                this.DebugLog("M3: RX delivered in-event (slot {0}), bit2 raised", radioEventSlot);
                // M4c: a scannable adv PDU (ADV_IND / ADV_SCAN_IND) triggers the HW's
                // autonomous SCAN_REQ when active scanning is programmed.
                var pduType = frame[0] & 0xF;
                if(pduType == AdvIndPduType || pduType == AdvScanIndPduType)
                {
                    // M5: an initiator (CONNECT_IND descriptor programmed) answers a
                    // connectable ADV_IND with CONNECT_IND instead of SCAN_REQ.
                    if(pduType != AdvIndPduType || !TrySendConnectInd(frame))
                    {
                        TrySendScanRequest(frame);
                    }
                }
                else if(pduType == ConnectIndPduType)
                {
                    // Delivered CONNECT_IND makes this node the slave: follow the hop
                    // sequence the LLData describes. Slave conn activity follows the adv
                    // activity, so its rx tag is 1 (silicon conn handle 0x0001).
                    connRole = ConnRole.Slave;
                    connActivityTag = 1;
                    // A CONNECT_IND ends the advertising event: no further channels.
                    advSequenceEpoch++;
                    advSequenceUntilHalfUs = 0;
                    connAccessAddress = ReadConnectIndAccessAddress(frame);
                    M5Trace($"slave connection established (ChSel={(frame[0] & ChSelBit) != 0})");
                }
                return;
            }
            if((frame[0] & 0xF) == ConnectIndPduType)
            {
                this.ErrorLog("M5: CONNECT_IND arrived but RX gate closed (eventLive={0}) — dropped", radioEventLive);
            }
            rxBuffer.Enqueue(new KeyValuePair<byte[], IRadio>(frame, sender));
        }

        private void DefineRegisters()
        {
            // reg_blecore RWBLECNTL control (0x000). r_rwip_driver_init performs the RW-BLE
            // master soft-reset handshake here (decoded via gdb at r_rwip_driver_init+270):
            //   lw a5,(0x60031000); a5 |= 0x80000000; sw; then `lw; bltz -> self` spins
            //   while bit31 stays set. Bit31 = MASTER_SOFT_RST, a self-clearing reset-request
            //   the hardware drops once the core reset completes. We complete it instantly:
            //   bit31 always reads 0 so the poll exits at once (a stored bit31 wedges the sim
            //   in a no-time-advance busy loop). The low 31 bits store/read-back so unrelated
            //   control bits (e.g. lld_core_init's RWBLE_EN=bit8) persist across the reset.
            // RWBLECNTL bit 27 is the software-interrupt request. r_rwip_sw_int_req
            // (0x4002f4b0) pre-acks INTACK 0x1000, enables INTCNTL 0x1000, then sets this
            // bit; the hardware answers by raising INTSTAT 0x1000, which r_rwble_isr routes
            // through r_rwip_isr to r_ip_funcs_p+0x2BC = r_rwip_sw_int_handler (pointer read
            // live off a devkit). It is how the controller re-enters its own kernel from
            // outside an event -- a self-directed interrupt, not a timer.
            //
            // The IDF 5.4.4 controller schedules through it and the 6.0.2 one does not, so
            // leaving it unimplemented stalled 5.4.4 the instant it first asked: the request
            // was accepted and never answered, the kernel never ran again, and the
            // peripheral programmed no events and advertised nothing for the rest of the
            // run. Silicon runs both controllers, so the bit is the hardware's obligation.
            Registers.Control.Define(this)
                .WithValueField(0, 31, out rwbleControl,
                    writeCallback: (_, v) =>
                    {
                        if((v & SwIntRequestBit) == 0)
                        {
                            return;
                        }
                        // Self-clearing: the request is consumed by raising the interrupt.
                        rwbleControl.Value = v & ~(ulong)SwIntRequestBit;
                        M5Trace("sw int requested (RWBLECNTL bit27)");
                        var ts = machine.LocalTimeSource;
                        ts.ExecuteInSyncedState(__ =>
                        {
                            if(RaiseStatusBit(SwIntBit))
                            {
                                M5Trace("sw int raised (INTSTAT 0x1000)");
                            }
                        }, new TimeStamp(ts.ElapsedVirtualTime, ts.Domain));
                    }, name: "RWBLECNTL")
                .WithFlag(31, FieldMode.Read | FieldMode.Write, valueProviderCallback: _ => false,
                    name: "MASTER_SOFT_RST"); // self-clearing: reset completes immediately

            // reg_blecore VERSION (0x004): lld_core_init (r_lld_core_init, lld.o) reads this
            // and asserts `== 0x09001b00` at lld.c:324 (decoded from libbtdm_app.a: the
            // fallthrough of `beq a5,a1,.L6` with a1=0x09001b00 calls the BLE assert with
            // line 324). Field layout is the RW-BLE family's BUILD[7:0]/UPG[15:8]/REL[23:16]/
            // TYP[31:24] (see RSLxx_Radio): TYP=0x09 (RW-BLE v9), UPG=0x1B. Read-only.
            Registers.Version.Define(this)
                .WithValueField(0, 32, FieldMode.Read, valueProviderCallback: _ => BleCoreVersion, name: "VERSION");

            // BT native clock, sampled via a capture handshake (decoded from
            // r_rwip_time_get in the C3 blob):
            //   read/modify 0x6003101C: firmware ORs in bit31 (capture request) and writes
            //   it back, then spins `bltz` until bit31 clears (capture done). The low 28
            //   bits are the 625us slot count. rwip_time_get is on nearly every timing/
            //   sleep path, so if this poll never completes the whole controller wedges.
            // We complete the capture instantly: bit31 always reads 0, low bits track sim
            // time. A write is accepted (the capture request) but changes nothing.
            Registers.BaseTimeCount.Define(this)
                .WithValueField(0, 28, FieldMode.Read,
                    valueProviderCallback: _ => (uint)(NowHalfMicroseconds() / HalfSlotHalfMicroseconds) & 0x0FFFFFFF, name: "BASETIMECNT")
                .WithReservedBits(28, 3)
                .WithFlag(31, FieldMode.Read, valueProviderCallback: _ => false, name: "SAMP"); // capture done immediately

            // Fine time within the half-slot, in HALF-microseconds: the firmware computes
            // elapsed = 624 - reg (decoded: `li a1,624; sub a1,a1,s1`), so store the
            // complement. 625 counts spanning one 312.5 us half-slot is what makes this
            // counter half-microsecond resolution, not microsecond.
            Registers.FineTimeCount.Define(this)
                .WithValueField(0, 10, FieldMode.Read,
                    valueProviderCallback: _ => (uint)((HalfSlotHalfMicroseconds - 1) - (NowHalfMicroseconds() % HalfSlotHalfMicroseconds)), name: "FINETIMECNT")
                .WithReservedBits(10, 22);

            // GROSSTIMETARGET (0x024): the slot the LL programs for its next scheduled
            // radio event (runtime-decoded: advances by the adv interval each event). We do
            // NOT arm off it — it is also written during init for non-adv timing, and firing
            // events/IRQs on every write stormed the sim. Kept as plain read-back storage;
            // the periodic ticker (StartAdvTicker) drives advertising instead.
            Registers.EventTarget.Define(this)
                .WithValueField(0, 32, valueProviderCallback: _ => eventTargetSlot,
                    writeCallback: (_, v) => eventTargetSlot = (uint)v, name: "GROSSTIMETARGET");

            // M5: 10ms kernel-timer target (INTSTAT bit 9 -> r_rwip_timer_10ms_handler via
            // r_modules_funcs_p[+712], live-resolved). The register is written in 10 ms
            // units; r_rwip_timer_10ms_set converts to base ticks with `param << 5`, which
            // is where TicksPer10Ms comes from. Enabled by the LL at connection setup for
            // its kernel timers (supervision etc.).
            Registers.GrossTimerTarget.Define(this)
                .WithValueField(0, 32, valueProviderCallback: _ => grossTarget,
                    writeCallback: (_, v) => { grossTarget = (uint)v; ArmEventTimer(ClockTargetBit, grossTarget * TicksPer10Ms); }, name: "GROSSTIMERTGT");

            // Interrupt controller (RW9 canonical offsets, same cluster as RSLxx_Radio;
            // confirm exact C3 offsets in the M1 fault-loop). INTCNTL=mask, INTSTAT=raw&mask,
            // INTRAWSTAT=raw, INTACK=write-1-clear. Masked+active RWBLE drives its matrix line.
            Registers.InterruptControl.Define(this)
                .WithValueField(0, 32, valueProviderCallback: _ => interruptMask,
                    writeCallback: (_, v) =>
                    {
                        interruptMask = (uint)v;
                        if((interruptMask & CscntBit) != 0 && !cscntArmed)
                        {
                            ScheduleCscnt();
                        }
                        // INTCNTL is written LAST in the timer-arm sequence (r_rwip_timer_hus_set
                        // writes the target regs then RMWs the enable bit in), so this is the
                        // effective arm point for the one-shot event timers.
                        ArmEventTimer(FineTimerBit, fineTarget);
                        ArmEventTimer(CoarseTimerBit, coarseTarget);
                        ArmEventTimer(ClockTargetBit, grossTarget * TicksPer10Ms);
                        UpdateInterruptLines();
                    }, name: "INTCNTL");
            Registers.InterruptStatus.Define(this)
                .WithValueField(0, 32, FieldMode.Read, valueProviderCallback: _ => rawStatus & interruptMask, name: "INTSTAT");
            Registers.InterruptRawStatus.Define(this)
                .WithValueField(0, 32, FieldMode.Read, valueProviderCallback: _ => rawStatus, name: "INTRAWSTAT");
            Registers.InterruptAcknowledge.Define(this)
                .WithValueField(0, 32, valueProviderCallback: _ => rawStatus,
                    writeCallback: (_, v) => { rawStatus &= ~(uint)v; UpdateInterruptLines(); }, name: "INTACK");

            // Interrupt PRIORITY/VECTOR register (0x2D8) — the M3 servicing unblock, load-bearing
            // for ANY RWBLE interrupt-driven feature (scan/connect). The shipped ESP-IDF
            // controller runs its ISR (r_rwble_isr_hack, r_ip_funcs_p+300) in "priority-dispatch"
            // mode (sdk_cfg_priv_opts+69 == 1), so instead of the plain INTSTAT (0x010) it reads
            // this register to obtain BOTH the active-interrupt bitmap AND a non-zero priority for
            // the highest pending source. Decoded from the ISR (0x40385e6a..90):
            //   priority = (reg >> 5) & 0x1F   -- must be != 0 or the ISR returns without ACK
            //   status   = (reg >> 10)         -- the interrupt bitmap fed to r_rwip_isr
            // i.e. reg = (INTSTAT << 10) | (priority << 5) | flags. Left as plain storage the
            // priority field reads 0, the ISR bails, the RWBLE line is never ACKed, and the whole
            // event-ISR chain storms and never runs. We synthesise it from the live masked status:
            // whenever an interrupt is pending we present its bitmap shifted into place with a
            // non-zero priority so the ISR dispatches and ACKs; when idle we read back what the
            // firmware stored.
            Registers.InterruptPriority.Define(this)
                .WithValueField(0, 32, valueProviderCallback: _ =>
                {
                    var active = rawStatus & interruptMask;
                    if(active == 0)
                    {
                        // Present priority==0 (bits 9:5) when nothing is pending: the ISR's
                        // dispatch loop keeps servicing while priority != 0, and reading back
                        // a stored value with a live priority field kept it spinning for the
                        // whole scan window (~10k blind ACKs of bit 11 per window, starving
                        // the next event's real fire).
                        return intPrioStored & ~0x3E0u;
                    }
                    return (active << 10) | (IntPriorityLevel << 5) | (intPrioStored & 0x1F);
                }, writeCallback: (_, v) => intPrioStored = (uint)v, name: "INTPRIO");

            // Deep-sleep: firmware writes DEEPSLCNTL then polls DEEPSLSTAT. We never sleep
            // (deterministic sim) -> report the core awake so the LL proceeds.
            Registers.DeepSleepStat.Define(this)
                .WithValueField(0, 32, FieldMode.Read, valueProviderCallback: _ => 0, name: "DEEPSLSTAT");

            // Event-anchor timers (M3 groundwork): the RW-BLE scheduler arms a one-shot timer for
            // the next radio event by writing its CLKN target here and enabling INTCNTL bit 11
            // (fine, near events / scan) or bit 10 (coarse, far events). Hardware raises the
            // matching INTSTAT bit when CLKN reaches the target; the ISR (via the 0x2D8 dispatch)
            // services the event. Decoded from r_rwip_timer_hus_set @0x4002f2a2 /
            // r_rwip_timer_hs_set @0x4002f214: 0x0e8=coarse target, 0x0ec=fine gross target (CLKN
            // slot), 0x0f0=fine sub-slot (624-us). Writing arms the comparator (effective once the
            // INTCNTL enable bit is also set). NOTE: this fires the FIRST scan-event start; driving
            // it continuously (scan re-arm -> RX -> 043e) is the deferred engine.
            Registers.CoarseTimerTarget.Define(this)
                .WithValueField(0, 32, valueProviderCallback: _ => coarseTarget,
                    writeCallback: (_, v) => { coarseTarget = (uint)v; ArmEventTimer(CoarseTimerBit, coarseTarget); }, name: "HSTIMERTGT");
            Registers.FineTimerTarget.Define(this)
                .WithValueField(0, 32, valueProviderCallback: _ => fineTarget,
                    writeCallback: (_, v) => { fineTarget = (uint)v; ArmEventTimer(FineTimerBit, fineTarget); }, name: "FINETIMERTGT");
            Registers.FineTimerSub.Define(this)
                .WithValueField(0, 32, valueProviderCallback: _ => fineTargetSub,
                    writeCallback: (_, v) => fineTargetSub = (uint)v, name: "FINETIMERTGTSUB");

            // --- Single-block AES engine (host crypto: SMP e(), key generation, RPA) ---
            // Decoded from ROM r_rwip_aes_encrypt (0x4002f3a2) and r_rwip_crypt_isr_handler
            // (0x4002eb94), which between them touch every register of this block:
            //   0x0B4..0x0C0  AESKEY, four 32-bit words written straight from the caller's
            //                 u32[4] key buffer (no byte swapping anywhere in the software
            //                 path -- r_rw_crypto_aes_encrypt just memcpys, so the engine
            //                 consumes the key in memory order)
            //   0x0C4         AESPTR, the EM *offset* of the 16-byte plaintext
            //   0x0B0 bit0    start
            // The ROM writes the plaintext to em(0x128) and sets AESPTR=0x128, then
            // r_rwip_crypt_evt_handler reads the result from em(0x138) -- so the engine
            // leaves the ciphertext one block PAST the plaintext rather than in place.
            // Completion raises INTSTAT bit 7, which r_rwip_aes_encrypt enables in INTCNTL
            // (|= 0x80) and pre-ACKs in INTACK (= 0x80) before starting.
            Registers.AesControl.Define(this)
                .WithValueField(0, 32, valueProviderCallback: _ => 0,
                    writeCallback: (_, v) => { if((v & 1) != 0) { RunAesBlock(); } }, name: "AESCNTL");
            for(var word = 0; word < AesKeyWords; word++)
            {
                var index = word;
                ((Registers)((long)Registers.AesKey0 + word * 4)).Define(this)
                    .WithValueField(0, 32, valueProviderCallback: _ => aesKey[index],
                        writeCallback: (_, v) => aesKey[index] = (uint)v, name: $"AESKEY{index}");
            }
            Registers.AesPtr.Define(this)
                .WithValueField(0, 32, valueProviderCallback: _ => aesPtr,
                    writeCallback: (_, v) => aesPtr = (uint)v, name: "AESPTR");

            // Programmed-event push. `r_sch_prog_ble_push` (ROM 0x40030bda) ends with
            //   _DAT_ram_60031100 = slot | 0x80000000;
            // i.e. the low 4 bits name the sch_prog slot software just filled and bit31
            // hands it to the hardware. The event's START TIME is not in this register --
            // it is in the slot, written by r_sch_prog_push (ROM 0x40030df6):
            //   +2..+5   28-bit start time as a CLKN slot count (625us), split lo16/hi12
            //   +6       624 - <us into that slot>, i.e. the complement FINETIMECNT reads
            //            (the ROM asserts the offset is <= 0x270 = 624; measured against a
            //             running bench the slot count reproduces wall time exactly, which
            //             is what settles slots vs half-slots)
            //   +10      duration, +12 priorities, +8 CS pointer, +14 from ble_push
            // This is the anchor the radio actually starts an event on, and it is entirely
            // in exchange memory where hardware can see it -- unlike the timer-comparator
            // guess the model currently opens its windows on.
            Registers.EventProgram.Define(this)
                .WithValueField(0, 32, valueProviderCallback: _ => 0,
                    writeCallback: (_, v) => OnEventProgrammed((uint)v), name: "EVTPRG");

            // Everything else in the 0x60031000 window (control, version, EM base/mapping,
            // scan/adv/RPA timers, coex, RF-test) is left to BasicDoubleWordPeripheral's
            // storage+unmapped-log default: config writes read back, and the Debug log of
            // unmapped reads is exactly what the M1 fault-loop uses to find the next
            // poll-with-expectation register to promote. Do NOT invent values here.
        }

        // Perform the one-shot AES-128-ECB the LL asked for and raise the completion
        // interrupt. Instant completion is faithful enough: the firmware always waits for
        // the CRYPT interrupt rather than polling a busy bit, so there is no observable
        // difference beyond latency, and the ISR runs on the next synced step.
        // Byte order flip between the AES block's little-endian operands and the
        // big-endian convention the AES primitive itself is defined over.
        private static byte[] Reversed(byte[] bytes)
        {
            var copy = (byte[])bytes.Clone();
            Array.Reverse(copy);
            return copy;
        }

        private void RunAesBlock()
        {
            var key = new byte[AesKeyWords * 4];
            for(var word = 0; word < AesKeyWords; word++)
            {
                BitConverter.GetBytes(aesKey[word]).CopyTo(key, word * 4);
            }
            var source = ResolveEmOffset(aesPtr);
            var destination = ResolveEmOffset(aesPtr + AesBlockLength);
            var plaintext = new byte[AesBlockLength];
            for(var i = 0; i < AesBlockLength; i++)
            {
                plaintext[i] = sysbus.ReadByte(source + (ulong)i);
            }
            // The RW-BLE AES block is little-endian: the link layer memcpy's SMP values
            // (which are transmitted least-significant-octet first) into AESKEY and the
            // plaintext buffer with no swap anywhere in the software path
            // (r_rw_crypto_aes_encrypt), yet the spec's security function e() is defined
            // over big-endian 128-bit integers (Core Vol 3 Part H 2.2.1). Silicon
            // reconciles the two, so the byte reversal lives in the hardware and belongs
            // here. Feeding the memory-order bytes to AES directly yields a session key
            // that is self-consistent between two of these models and wrong against every
            // other stack -- which is exactly how it escaped notice.
            using(var aes = AesProvider.GetEcbProvider(Reversed(key)))
            {
                var block = Block.UsingBytes(Reversed(plaintext));
                aes.EncryptBlockInSitu(block);
                var output = Reversed(block.Buffer);
                for(var i = 0; i < AesBlockLength; i++)
                {
                    sysbus.WriteByte(destination + (ulong)i, output[i]);
                }
                M5Trace($"aes em=0x{aesPtr:X} -> 0x{aesPtr + AesBlockLength:X} out={BitConverter.ToString(block.Buffer)}");
            }
            RaiseStatusBit(CryptBit);
        }

        // --- Interrupt plumbing -------------------------------------------------

        // GPIO 0 <- ESP32_RwBleDeepSleep wake pulse. The ROM r_rwip_isr routes BLEINTSTAT bit 3
        // to r_rwip_wakeup, so a deep-sleep wake-up is that status bit, masked by INTCNTL
        // like every other source.
        public void OnGPIO(int number, bool value)
        {
            if(number == 0 && value)
            {
                RaiseStatusBit(SleepBit);
            }
        }

        private void UpdateInterruptLines()
        {
            // For M1 the whole controller rides RWBLE (source 8). Per-source demux
            // (RWBT/BT_MAC/BT_BB) is added when the event engine needs distinct lines.
            Connections[RwbleLine].Set((rawStatus & interruptMask) != 0);
        }

        // The push to 0x60031100 hands a programmed slot to the radio. This is the ONLY
        // thing that starts a radio event: the hardware turns the receiver on at the
        // slot's start time and off `duration` later, and the link layer times everything
        // it does from those two fields. So the model schedules from them too — there is
        // no window length, TX delay or event ticker of ours in this path.
        private void OnEventProgrammed(uint value)
        {
            if((value & EventProgramGoBit) == 0)
            {
                return;
            }
            EnsureConEnvTimeline();
            var slot = (int)(value & 0xF);
            var seg0Base = ResolveEmSegment(EmSegSchProg);
            if(seg0Base == 0)
            {
                return;
            }
            var slotAddr = seg0Base + (ulong)slot * SchProgSlotStride;
            var startHalfUs = SlotStartHalfMicroseconds(slotAddr);
            // The establishment event is the one exception to "the programmed slot start IS
            // the anchor". Its packet has to fall inside the transmit window, which per
            // §4.5.3 opens transmitWindowDelay (1.25 ms) + WinOffset after the CONNECT_IND;
            // but the anchor the LL programs for it comes out of cal_con_timestamp as the
            // interval grid point, and the WinOffset it emits alongside is (anchor-ref54)/4.
            // Substituting one into the other, window start == anchor + transmitWindowDelay
            // identically, for any ref54 -- the LL always programs this event exactly one
            // transmitWindowDelay short of the window it just advertised. Silicon transmits
            // inside that window on every establishment (14/14 captured with an nRF
            // Sniffer), so the radio applies the offset, not the link layer: what the LL
            // programs here is the window reference, and the hardware opens the window a
            // fixed delay later. The whole event moves, not just its packet -- the slave's
            // reply arrives T_IFS after a transmission that is itself delayed.
            // The deferral moves the GRID, not just the establishment packet. Deferring
            // only the first event left every later one on the undeferred origin, so the
            // first gap came out one transmitWindowDelay short of connInterval while every
            // gap after it was exact. Silicon does not do that: 52 establishments across
            // two sniffer captures (50 ms x15 and 30 ms x37, hil/nrf-ble-link-oracle/
            // EXP-anchor-grid.md) put consecutive central transmissions exactly
            // connInterval apart starting from the first one, and never once at
            // connInterval - 1.25 ms. Vol 6 Part B 4.5.4 says the same: the first packet
            // sent DEFINES the anchor, and the second anchor shall be connInterval after
            // it. The firmware's own state agrees -- firstevt_probe measured the blob
            // advancing its anchor variable (evtincr==1), so the whole grid moves with it.
            if(connRole == ConnRole.Master && IsConnectionEventSlot(slotAddr, out _))
            {
                if(firstConnEventTxPending)
                {
                    firstConnEventTxPending = false;
                    connSlotDeferralHalfUs = TransmitWindowDelayHalfUs;
                    // Nothing advances the event counter here. The LL's own connection
                    // env reports evtcnt=0 for this event (see the conenv trace line), so
                    // the establishment event IS event 0 no matter how far ahead of the
                    // CONNECT_IND it sits -- what carries that distance to the peer is the
                    // advertised WinOffset, not a counter the firmware never incremented.
                    // An earlier revision advanced the counter here to paper over a
                    // WinOffset that had been folded modulo the interval; the fold is
                    // fixed at its source in SendConnectIndFromDescriptor.
                    M5Trace($"evt establishment: start deferred by transmitWindowDelay to {(startHalfUs + connSlotDeferralHalfUs) / 2}us");
                }
                startHalfUs += connSlotDeferralHalfUs;
            }
            var nowHalfUs = NowHalfMicroseconds();
            var durHalfUs = (ulong)sysbus.ReadWord(slotAddr + SchProgDurationOffset);
            M5Trace($"evt programmed slot={slot} start={startHalfUs / 2}us now={nowHalfUs / 2}us "
                + $"lead={((long)startHalfUs - (long)nowHalfUs) / 2}us dur={durHalfUs / 2}us "
                + $"end={(startHalfUs + durHalfUs) / 2}us ctrl=0x{sysbus.ReadWord(slotAddr):X4}");

            // RX window widening (BT Core Vol 6 Part B §4.5.7): the receiver is turned on
            // this many half-us BEFORE the programmed anchor, so a peer whose idea of the
            // anchor differs -- by clock drift, or because the two ends derived it from the
            // CONNECT_IND slightly differently -- is still heard. The firmware supplies the
            // amount in CS+0x1a and recomputes it every event, so the model reads it rather
            // than owning a window of its own.
            var wideningHalfUs = ConnRxWindowWideningHalfUs(slotAddr);
            var openHalfUs = startHalfUs > wideningHalfUs ? startHalfUs - wideningHalfUs : 0;
            // CS+0x1a (RXWINCNTL) is a half-width in us, symmetric about the anchor, and the
            // programmed start sits one half-width early, so the receiver stays on until
            // start + 2 * width even when the sch_prog duration is shorter.
            var rxWindowHalfUs = 4 * wideningHalfUs;
            if(rxWindowHalfUs > durHalfUs)
            {
                M5Trace($"evt rx window: end extended from {(startHalfUs + durHalfUs) / 2}us "
                    + $"to {(startHalfUs + rxWindowHalfUs) / 2}us (CS+0x1a={wideningHalfUs}us)");
                durHalfUs = rxWindowHalfUs;
            }

            // sch_prog is a push QUEUE, not a single register: the LL pipelines pushes,
            // handing the next event over while the current one is still on air (the
            // extended-scan schedule pushes each 625 us micro-event during its
            // predecessor). Superseding the live event here dropped its END, the slot
            // was never reaped, and the LL's scheduling queue wedged for good. Queue
            // the push instead; EndRadioEvent drains it in order, like the hardware.
            var pending = new PendingRadioEvent
            {
                Slot = slot,
                Seg0Base = seg0Base,
                OpenHalfUs = openHalfUs,
                DurHalfUs = durHalfUs + wideningHalfUs,
                WideningHalfUs = wideningHalfUs,
            };
            if(radioEventLive || radioEventScheduled)
            {
                pendingRadioEvents.Enqueue(pending);
                M5Trace($"evt queued slot={slot} depth={pendingRadioEvents.Count}");
                return;
            }
            ScheduleRadioEvent(pending);
        }

        // Opening early must not move the transmission: the anchor is where this node
        // transmits, and the widening only extends the listening edge. The duration is
        // extended by the same amount so the event still ENDs where the firmware
        // programmed it. Only the early edge is modelled -- the firmware's own duration
        // (1947 us for what is a ~300 us exchange) already covers the late edge.
        private void ScheduleRadioEvent(PendingRadioEvent pending)
        {
            // A start already in the past means the LL programmed late; the hardware would
            // run the event immediately rather than skip it.
            var nowHalfUs = NowHalfMicroseconds();
            var delayHalfUs = pending.OpenHalfUs > nowHalfUs ? pending.OpenHalfUs - nowHalfUs : 0;
            radioEventEpoch++;
            radioEventScheduled = true;
            var epoch = radioEventEpoch;
            var ts = machine.LocalTimeSource;
            var when = LocalDelay(delayHalfUs);
            ts.ExecuteInSyncedState(
                _ => BeginRadioEvent(pending.Slot, pending.Seg0Base, pending.DurHalfUs, pending.WideningHalfUs, epoch), when);
        }

        // Event start: the radio is on for this slot. The control structure the slot points
        // at supplies channel/AA/CRC, and the TX descriptor goes out now — real RW hardware
        // transmits at the event's own start, not some interval after it.
        private void BeginRadioEvent(int slot, ulong seg0Base, ulong durHalfUs, ulong wideningHalfUs, ulong epoch)
        {
            if(epoch != radioEventEpoch)
            {
                return; // superseded by a later push before this one started
            }
            radioEventScheduled = false;
            radioEventLive = true;
            consecutiveCrcErrors = 0;
            radioEventSlot = slot;
            radioEventStartHalfUs = NowHalfMicroseconds();
            radioEventSeg0Base = seg0Base;
            radioEventCtrlAddr = seg0Base + (ulong)slot * SchProgSlotStride;
            M5Trace($"evt start slot={slot} ctrl=0x{sysbus.ReadWord(radioEventCtrlAddr):X4}");
            if(connRole != ConnRole.None && TryResolveConnControlStructure(out var winCs))
            {
                M5Trace($"evt win: role={connRole} cs=0x{winCs:X}"
                    + $" +0x16=0x{sysbus.ReadWord(winCs + 0x16):X4}"
                    + $" +0x18=0x{sysbus.ReadWord(winCs + 0x18):X4}"
                    + $" +0x1a=0x{sysbus.ReadWord(winCs + 0x1a):X4}"
                    + $" +0x1e=0x{sysbus.ReadWord(winCs + 0x1e):X4}"
                    + $" +0x20=0x{sysbus.ReadWord(winCs + 0x20):X4}"
                    + $" +0x50=0x{sysbus.ReadWord(winCs + 0x50):X4}");
                TraceConEnv();
            }
            // Which physical channel the radio comes up on is a property of the event
            // the scheduler is starting, not of anything latched when a link was
            // established: after a disconnect the same node's scheduler goes straight
            // back to advertising and scanning events, and a channel left parked on
            // a data channel would make it deaf and inaudible for good. A connection
            // event hops, with the channel read from the control structure the slot
            // names (see DataChannelFromControlStructure).
            if(IsConnectionEventSlot(radioEventCtrlAddr, out var eventCs))
            {
                currentChannel = DataChannelFromControlStructure(eventCs);
                M5Trace($"conn event {sysbus.ReadWord(eventCs + CsEventCounterOffset)}: ch {currentChannel}"
                    + $" (HOPCNTL=0x{sysbus.ReadWord(eventCs + CsHopControlOffset):X4})");
            }
            else
            {
                currentChannel = AdvChannel37;
            }
            TryAdvTxAtEventStart();
            var ts = machine.LocalTimeSource;
            if(wideningHalfUs == 0)
            {
                TryConnEventTx();
            }
            else
            {
                // The radio came on `wideningHalfUs` early to listen; transmit at the anchor.
                var txAt = LocalDelay(wideningHalfUs);
                ts.ExecuteInSyncedState(_ =>
                {
                    if(radioEventLive && epoch == radioEventEpoch)
                    {
                        TryConnEventTx();
                    }
                }, txAt);
            }

            var when = LocalDelay(durHalfUs);
            ts.ExecuteInSyncedState(_ => EndRadioEvent(epoch), when);
        }

        // Event end: the radio goes off after the programmed duration. If the slot is still
        // armed, transition it to the observed post-service sentinel (0x0018 = fields
        // cleared, STATE=3) and raise END (bit 5), which is what dispatches
        // r_sch_prog_end_isr and lets the LL reap the slot and program the next event.
        private void EndRadioEvent(ulong epoch)
        {
            if(!radioEventLive || epoch != radioEventEpoch)
            {
                return;
            }
            // An event does not end while a frame it put on air is still transmitting:
            // the RW scheduler's END fires after the frame completes, and the LL's EOF
            // path reads state (the CONNECT_IND descriptor's txdone, which this model
            // raises one air-time after the send instant) that only exists once the
            // frame is done. Ending at the programmed duration regardless made the LL
            // race its own transmission: an ADV_IND answered near the window's edge had
            // its txdone land after the EOF read it, the initiator concluded nothing
            // went out, and it re-initiated forever instead of creating the connection.
            var nowHalfUs = NowHalfMicroseconds();
            // Likewise an advertising event runs until its last channel's slot has passed
            // (see SendAdvOnChannel).
            var holdUntilHalfUs = Math.Max(Math.Max(txInFlightUntilHalfUs, rxInFlightUntilHalfUs), advSequenceUntilHalfUs);
            if(holdUntilHalfUs > nowHalfUs)
            {
                var ts = machine.LocalTimeSource;
                ts.ExecuteInSyncedState(_ => EndRadioEvent(epoch), LocalDelay(holdUntilHalfUs - nowHalfUs));
                return;
            }
            advSequenceUntilHalfUs = 0;
            var wasArmed = IsEventSlotArmed();
            radioEventLive = false;
            if(wasArmed)
            {
                M5Trace($"evt end slot={radioEventSlot} ctrl=0x{sysbus.ReadWord(radioEventCtrlAddr):X4}");
                DumpConnectIndLlData("evt end");
                sysbus.WriteWord(radioEventCtrlAddr, SchProgSlotServiced);
                RaiseStatusBit(EndBit);
            }
            // The hardware moves on to the next queued push as this event retires.
            if(pendingRadioEvents.Count > 0)
            {
                ScheduleRadioEvent(pendingRadioEvents.Dequeue());
            }
        }

        // Diagnostic only (C3BLE_TRACE): re-read the CONNECT_IND TX descriptor's LLData.
        // The model reads those 22 bytes when the ADV_IND lands and puts them on air a
        // T_IFS later, but the ROM computes the connection anchor on the frame-EOF path
        // (r_lld_init_process_pkt_tx, 0x4001e132) which runs after the event ends. If the
        // firmware rewrites WinOffset to match that anchor, the bytes here will differ
        // from the ones we transmitted.
        private void DumpConnectIndLlData(string tag)
        {
            if(connectIndDataPtr == 0)
            {
                return;
            }
            var lldata = new byte[22];
            for(var i = 0; i < lldata.Length; i++)
            {
                lldata[i] = sysbus.ReadByte(connectIndDataPtr + (ulong)i);
            }
            M5Trace($"{tag}: connind lldata now=" + BitConverter.ToString(lldata)
                + $" | WinSize={lldata[7]} WinOffset={lldata[8] | (lldata[9] << 8)}"
                + $" Interval={lldata[10] | (lldata[11] << 8)}");
        }

        // RX window widening for the connection event a slot is about to run, in
        // half-microseconds, read from that event's own control structure at CS+0x1a.
        //
        // Identified by watching the field across the first connection events: on a slave it
        // reads 1337, 1387, 1437 -- growing by exactly 50 per event that goes unheard -- and
        // collapses to 97 the moment a packet is finally received and the anchor re-syncs.
        // A master, which is the timing reference and never widens, holds a constant 30.
        // The 50-per-event growth fixes the scale: combined sleep-clock accuracy of 500 ppm
        // over a 50 ms interval is 25 us of accumulated uncertainty per event, so 50 units
        // is 25 us and one unit is half a microsecond -- the same base the slot start and
        // duration already use.
        //
        // Without this the model gated reception on the programmed anchor exactly, so a
        // peer transmitting even 1 us early was silently lost. That is not what the radio
        // does, and it is why the peripheral missed its first two connection events while
        // silicon misses none.
        // CS+0x1a only means window widening on a CONNECTION control structure. The same
        // offset in an advertising, scanning or initiating CS is a different field, so the
        // slot has to be identified before the value is trusted: connRole alone is not
        // enough, because it stays set while those other activities run (and is never
        // cleared on disconnect), and reading the wrong field there shifts the event start
        // by a garbage amount -- observed as `BLE assert lld_scan.c 2117` about 18 ms after
        // a central resumes scanning, and the equivalent in lld_adv / lld_init.
        //
        // The discriminator is the hop increment in CS+0x16 bits[12:8]. BT Core Vol 6 Part B
        // section 4.5.8.2 constrains hopIncrement to 5..16 for a connection, and an
        // advertising or scanning CS -- which uses the three fixed advertising channels and
        // never hops -- does not carry one in that range. Spec-defined, and read from the
        // firmware's own field rather than assumed.
        private ulong ConnRxWindowWideningHalfUs(ulong slotAddr)
        {
            return IsConnectionEventSlot(slotAddr, out var cs)
                ? sysbus.ReadWord(cs + CsRxWindowWideningOffset)
                : 0UL;
        }

        // Is the event this slot is about to run a CONNECTION event?
        //
        // The access address in the CS answers it outright: every advertising,
        // scanning and initiating event uses the one fixed advertising access
        // address 0x8E89BED6 (BT Core Vol 6 Part B §2.1.2), and a connection uses
        // the session AA the initiator generated. Asking the CS the running slot
        // points at is also the only form of the question that stays true across a
        // link teardown -- connRole and the channel the model parked on are latched
        // when a link comes up and outlive it, the CS the scheduler hands over does
        // not.
        private bool IsConnectionEventSlot(ulong slotAddr, out ulong cs)
        {
            cs = 0;
            var csOffset = (uint)sysbus.ReadWord(slotAddr + SchProgCsPtrOffset) * 2;
            if(csOffset < ControlStructureRegionOffset)
            {
                return false;
            }
            cs = ResolveEmOffset(csOffset);
            if(cs == 0)
            {
                return false;
            }
            var accessAddress = sysbus.ReadDoubleWord(cs + CsAccessAddressOffset);
            return accessAddress != AdvAccessAddress && accessAddress != 0;
        }

        // The link layer's own view of the connection, read straight out of its RAM
        // structures. This is the simulator-side counterpart of the anchor probe the HIL
        // bench compiles into the firmware (open-source/e-ink/hil-c3ble/anchor_probe.h) --
        // same struct, same offsets, so the two logs diff field-for-field.
        //
        // Reading it here rather than from an instrumented firmware is not just
        // convenience, it is the only way to measure the sim at all: the 1 ms esp_timer
        // the firmware probe needs costs nothing on silicon (connection rate unchanged at
        // 0.38/s with and without it) but takes this model from four connections in a
        // twelve-second run to zero. A model with that little timing margin cannot be
        // measured by anything that perturbs it.
        //
        // The establishment values are the ones worth comparing, and they are transients:
        // lastsync is rewritten on every sync. Silicon holds, on every connection and both
        // roles, anchor - lastsync == interval - 2 with evtincr == 1 -- the LL skips the
        // advertised transmit window entirely and takes the following interval. The
        // sample with evtcnt == 0 is the one to read.
        private void TraceConEnv()
        {
            if(tracePath == null)
            {
                return;
            }
            for(var link = 0; link < 2; link++)
            {
                var env = sysbus.ReadDoubleWord(lldConEnv + (ulong)link * 4);
                if(env < 0x3fc00000 || env >= 0x3fd00000)
                {
                    continue;
                }
                var anchor = sysbus.ReadDoubleWord(env + 0x48);
                var lastsync = sysbus.ReadDoubleWord(env + 0x50);
                M5Trace($"conenv link{link} env=0x{env:X} anchor={anchor} lastsync={lastsync}"
                    + $" delta={(anchor - lastsync) & 0x0fffffff}"
                    + $" interval={sysbus.ReadDoubleWord(env + 0x64)}"
                    + $" winoff4={sysbus.ReadDoubleWord(env + 0x60)}"
                    + $" winsize={sysbus.ReadWord(env + 0x70)}"
                    + $" finewin={sysbus.ReadWord(env + 0x6e)}"
                    + $" evtcnt={sysbus.ReadWord(env + 0x7c)}"
                    + $" evtincr={sysbus.ReadWord(env + 0x7e)}");
            }
        }

        // --- Establishment timeline: the model-side twin of the HIL firstevt probe -----
        //
        // TraceConEnv() above samples at event start, which is one sample per connection
        // event -- far too coarse to see the establishment window, where silicon does all
        // its interesting work (lastsync re-syncing forward, CLKN overtaking the window
        // anchor, the skip). open-source/e-ink/hil-c3ble/firstevt_probe.h samples the same
        // fields on silicon every 200 us; this is the same probe on this side of the glass,
        // emitting the same field order so the two logs diff row-for-row.
        //
        // Sampling here is FREE in a way the firmware probe can never be: these are
        // emulator-side reads that consume no guest cycles, whereas the firmware's 1 ms
        // esp_timer takes this model from four connections in twelve seconds to zero. So
        // this runs at half-slot resolution without perturbing what it measures.
        //
        // Only changed tuples are emitted, so a quiet connection costs one line per event.
        private void EnsureConEnvTimeline()
        {
            if(tracePath == null || conEnvTimelineRunning)
            {
                return;
            }
            conEnvTimelineRunning = true;
            ScheduleConEnvSample();
        }

        private void ScheduleConEnvSample()
        {
            var ts = machine.LocalTimeSource;
            var when = LocalDelay(HalfSlotHalfMicroseconds);
            ts.ExecuteInSyncedState(_ =>
            {
                SampleConEnvTimeline();
                ScheduleConEnvSample();
            }, when);
        }

        private void SampleConEnvTimeline()
        {
            var clkn = (uint)(NowHalfMicroseconds() / HalfSlotHalfMicroseconds) & ClknMask;
            for(var link = 0; link < 2; link++)
            {
                var env = sysbus.ReadDoubleWord(lldConEnv + (ulong)link * 4);
                if(env < 0x3fc00000 || env >= 0x3fd00000)
                {
                    conEnvTimelineLast[link] = null;
                    continue;
                }
                var anchor = sysbus.ReadDoubleWord(env + 0x48);
                var lastsync = sysbus.ReadDoubleWord(env + 0x50);
                var interval = sysbus.ReadDoubleWord(env + 0x64);
                var winoff4 = sysbus.ReadDoubleWord(env + 0x60);
                var evtcnt = sysbus.ReadWord(env + 0x7c);
                var evtincr = sysbus.ReadWord(env + 0x7e);
                var key = $"{anchor}/{lastsync}/{interval}/{winoff4}/{evtcnt}/{evtincr}";
                if(conEnvTimelineLast[link] == key)
                {
                    continue;
                }
                conEnvTimelineLast[link] = key;
                M5Trace($"cetl link{link} clkn={clkn} anchor={anchor} lastsync={lastsync}"
                    + $" lead={SignedClkn(anchor - clkn)} dsync={SignedClkn(anchor - lastsync)}"
                    + $" itvl={interval} woff4={winoff4} evtcnt={evtcnt} evtincr={evtincr}");
            }

            // The initiator env is the master's side of the same question, and it is FREED
            // once the connection is up -- so it has to be sampled here, on the timeline,
            // rather than looked up afterwards. +0x54 is the reference time
            // r_lld_init_process_pkt_rx_adv_ind derives from the ADV_IND RX descriptor, and
            // r_lld_init_process_pkt_tx_cal_con_timestamp computes BOTH the master's anchor
            // and the WinOffset it emits from it. If the master's slot start is wrong, this
            // is the value to compare against the timestamp the model actually wrote.
            var ini = sysbus.ReadDoubleWord(lldInitEnv);
            if(ini >= 0x3fc00000 && ini < 0x3fd00000)
            {
                var refTs = sysbus.ReadDoubleWord(ini + 0x54);
                var key = $"{refTs}";
                if(initEnvTimelineLast != key)
                {
                    initEnvTimelineLast = key;
                    M5Trace($"ietl clkn={clkn} initenv=0x{ini:X} ref54={refTs}"
                        + $" delta_now={SignedClkn(refTs - clkn)}"
                        + $" rate4e={sysbus.ReadByte(ini + 0x4e)} rxflag50={sysbus.ReadByte(ini + 0x50)}");
                }
            }
            else
            {
                initEnvTimelineLast = null;
            }
        }

        // CLKN is a 28-bit wrapping counter, so a difference is only meaningful once the
        // top half of the range is read as negative -- same sign-extension the HIL probe does.
        private static long SignedClkn(uint diff)
        {
            var masked = diff & ClknMask;
            return masked > (ClknMask >> 1) ? (long)masked - ((long)ClknMask + 1) : masked;
        }

        // Programmed start time of a sch_prog slot, in half-microseconds on the same base
        // as NowHalfMicroseconds(). See the EventProgram register comment for the layout.
        private ulong SlotStartHalfMicroseconds(ulong slotAddr)
        {
            var halfSlots = (ulong)sysbus.ReadWord(slotAddr + 2)
                | ((ulong)(sysbus.ReadWord(slotAddr + 4) & 0x0FFF) << 16);
            // +6 holds the sub-half-slot target the way FINETIMECNT reads it — as the
            // complement (624 - elapsed) — so the event starts this many half-us in.
            var fineHalfUs = (ulong)(SchProgFineMax - sysbus.ReadWord(slotAddr + 6));
            return halfSlots * HalfSlotHalfMicroseconds + fineHalfUs;
        }

        // --- M3 groundwork: event-anchor one-shot timers -----------------------
        // Arm a one-shot comparator that fires INTSTAT `statusBit` when CLKN reaches
        // `target` (a 28-bit slot count), but only if that bit is enabled in INTCNTL.
        // Each arm bumps a per-bit epoch; the scheduled callback fires only if it is
        // still the latest arm and still enabled, so re-arms/disables never storm
        // (Renode sync callbacks can't be cancelled, hence the epoch/enable re-check).
        private void ArmEventTimer(uint statusBit, uint target)
        {
            M5Trace($"arm bit={statusBit:X} target={target:X} mask={interruptMask:X} raw={rawStatus:X}");
            if((interruptMask & statusBit) == 0)
            {
                return; // not enabled yet — the INTCNTL write will re-arm once it is
            }
            target &= ClknMask;
            if(target == ClknMask)
            {
                return; // -1 sentinel => disarm
            }
            // M3 subsystem 2 (priority-interrupt delivery, docs/esp32c3-ble-m3-continuous-scan.md
            // §4.2): if the firmware re-programs the SAME (target, mask) that is already armed
            // and still pending/un-fired, this is a re-program of an already-past target, not a
            // fresh event — do not reschedule (that is the "re-fire on target already <= CLKN"
            // storm the doc calls out at §3.4/§3b). Only a genuinely new target or a newly
            // enabled mask re-arms.
            var armKey = (target, interruptMask);
            if(lastArmed.TryGetValue(statusBit, out var prevArmKey) && prevArmKey.Item1 == armKey.Item1
                && prevArmKey.Item2 == armKey.Item2 && (rawStatus & statusBit) == 0)
            {
                return;
            }
            lastArmed[statusBit] = armKey;

            var clkn = (uint)(NowHalfMicroseconds() / HalfSlotHalfMicroseconds) & ClknMask;
            var slots = (long)target - clkn;
            if(statusBit == ClockTargetBit)
            {
                // The 10ms kernel timer (r_rwip_timer_10ms_handler) is a wrap-aware CLKN
                // equality comparator: a target in the past does NOT fire until the handler
                // re-programs a fresh one (firing immediately on the stale init-time target
                // re-fire-stormed, M5 fault-loop). "Past" = more than half the 28-bit range.
                var delta = (ulong)(((long)target - clkn) & ClknMask);
                if(delta > (ClknMask >> 1))
                {
                    return;
                }
                slots = (long)delta;
            }
            else if(slots < 0)
            {
                slots = 0; // target already passed — fire on the next synced instant
            }
            var delayHalfUs = (ulong)slots * HalfSlotHalfMicroseconds;

            timerEpoch.TryGetValue(statusBit, out var prev);
            var epoch = prev + 1;
            timerEpoch[statusBit] = epoch;

            var ts = machine.LocalTimeSource;
            var when = LocalDelay(delayHalfUs);
            ts.ExecuteInSyncedState(_ => OnEventTimer(statusBit, epoch), when);
        }

        private void OnEventTimer(uint statusBit, ulong epoch)
        {
            // Stale (re-armed since scheduling) or disabled meanwhile => do nothing.
            if(!timerEpoch.TryGetValue(statusBit, out var current) || current != epoch)
            {
                return;
            }
            if((interruptMask & statusBit) == 0)
            {
                return;
            }
            // Priority-interrupt delivery (M3 subsystem 2, docs/esp32c3-ble-m3-continuous-scan.md
            // §4.2): if this bit is already pending and un-ACKed, do not raise it again — a
            // firmware re-program of an already-past target must not look like a fresh event to
            // the ISR (that is the "re-fire on target already <= CLKN" storm the doc calls out).
            // RaiseStatusBit is a no-op in that case.
            lastArmed.Remove(statusBit);
            if(statusBit == ClockTargetBit && tracePath != null)
            {
                var modp = sysbus.ReadDoubleWord(modulesFuncsP);
                M5Trace($"clk-target fire: handler=0x{sysbus.ReadDoubleWord(modp + 712):X8}");
            }
            // Raise the event-anchor interrupt; the firmware services it via the 0x2D8
            // dispatch and runs its event-start callback, which programs a sch_prog slot and
            // pushes it. The radio event itself starts from that push (OnEventProgrammed),
            // not from this interrupt — on hardware this comparator only wakes the link
            // layer up, it does not turn the radio on.
            RaiseStatusBit(statusBit);
        }

        // Set an INTSTAT bit and update the interrupt line, but only if it is not already
        // pending (un-ACKed). Returns true if the bit transitioned 0->1. See OnEventTimer.
        // CSCNT (BLEINTSTAT bit 0): the RW core's slot-clock interrupt, one per 625-us slot
        // while INTCNTL bit 0 is set. The controller enables it in r_rwip_wakeup and the ROM
        // r_rwip_isr routes it to r_rwip_wakeup_end while a wake-up is in progress
        // (modules_funcs 0x2e4); rwip_wakeup_end masks it again.
        private void ScheduleCscnt()
        {
            cscntArmed = true;
            var ts = machine.LocalTimeSource;
            var when = LocalDelay(HalfSlotHalfMicroseconds * 2);
            ts.ExecuteInSyncedState(_ =>
            {
                if((interruptMask & CscntBit) == 0)
                {
                    cscntArmed = false;
                    return;
                }
                RaiseStatusBit(CscntBit);
                ScheduleCscnt();
            }, when);
        }

        private bool cscntArmed;
        private bool txConfirmedByRx;
        // Advertising sequence state (see SendAdvOnChannel): the generation that pending
        // channel transmissions must still match, and the instant the event may end.
        private ulong advSequenceEpoch;
        private ulong advSequenceUntilHalfUs;
        // Receptions between their first and last bit (see BeginReception), the latest end
        // among them, and the run of CRC failures in the current connection event.
        private readonly List<Reception> receptionsInFlight = new List<Reception>();
        private ulong rxInFlightUntilHalfUs;
        private int consecutiveCrcErrors;

        private sealed class Reception
        {
            public byte[] Frame;
            public IRadio Sender;
            public ulong StartHalfUs;
            public ulong EndHalfUs;
            public bool CrcError;
        }

        private bool RaiseStatusBit(uint statusBit)
        {
            if((rawStatus & statusBit) != 0)
            {
                return false;
            }
            rawStatus |= statusBit;
            UpdateInterruptLines();
            return true;
        }

        // Blob ctrl-word layout (decoded from r_sch_prog_ble_push_hack 0x40386858 store site
        // 0x403869c6 + reader r_sch_prog_end_isr_handler 0x4038651a — NOT the open-source RW
        // sch_prog.c layout): TYPE = bits[15:11], STATE = bits[5:3], bit1 = "pushed/valid"
        // marker (ori a5,a5,2 on both compose paths). A freshly-armed RX slot is STATE==0
        // with bit1 set (observed 0x2802 = TYPE 5); a serviced/reaped slot is STATE==3
        // (observed idle 0x0018). The END ISR only dispatches STATE in {3,4,5}.
        private bool IsRxGateOpen()
        {
            return radioEventLive && IsEventSlotArmed();
        }

        // The slot this event was pushed with is known exactly — it came in on the push
        // register — so its control word is read directly rather than searched for.
        private bool IsEventSlotArmed()
        {
            if(!radioEventLive)
            {
                return false;
            }
            var ctrl = sysbus.ReadWord(radioEventCtrlAddr);
            // STATE 0 = armed and waiting, 2 = frame in progress (we advance it there on RX
            // delivery, mirroring the hardware).
            var state = (ctrl >> 3) & 0x7;
            return (state == 0 || state == 2) && (ctrl & 0x2) != 0;
        }


        private void WriteCtrlType(ulong ctrlAddr, ushort type)
        {
            var ctrl = sysbus.ReadWord(ctrlAddr);
            ctrl = (ushort)((ctrl & ~SchProgTypeMask) | ((type << 3) & SchProgTypeMask));
            sysbus.WriteWord(ctrlAddr, ctrl);
        }

        // --- M2/M5 advertising TX event engine ---------------------------------
        // Adv PDUs go out at the programmed event's start, which is where real RW hardware
        // transmits them: the slot handed over on the push says when the radio turns on,
        // and the first thing it does is send the TX descriptor. The peer's T_IFS response
        // (SCAN_REQ / CONNECT_IND) then lands inside this same event, which is what the
        // delivery gate requires.
        private void TryAdvTxAtEventStart()
        {
            if(radioEventCtrlAddr != 0 && IsConnectionEventSlot(radioEventCtrlAddr, out _))
            {
                return; // connection events own the radio; the slave's stale adv
                        // descriptors must not re-broadcast (and must not re-park on 37)
            }
            var pdu = BuildAdvPdu();
            if(pdu == null)
            {
                return; // not an advertiser (scan/init CS rings carry no adv-type descriptor)
            }
            TryResolveArmedControlStructure(out var cs, out _);
            var channels = AdvChannelSequence(cs);
            if(channels.Count == 0)
            {
                this.WarningLog("Advertising control structure enables no advertising channel (CS+0x26 bits 7:5 clear); nothing sent");
                return;
            }
            var spacingHalfUs = AdvPacketSpacingMicroseconds() * 2;
            advSequenceEpoch++;
            var startHalfUs = NowHalfMicroseconds();
            advSequenceUntilHalfUs = startHalfUs + (ulong)channels.Count * spacingHalfUs;
            SendAdvOnChannel(pdu, channels, 0, startHalfUs, spacingHalfUs, advSequenceEpoch, radioEventEpoch);
        }

        // One advertising event transmits the same PDU on every channel the control structure
        // enables, in the hardware's channel order, one ADV-to-ADV interval apart, and listens
        // on each channel in between for a SCAN_REQ or CONNECT_IND (BT Core Vol 6 Part B
        // §4.4.2). Both inputs come from the firmware:
        //
        //   CS+0x26 bits 7:5   advertising channel map, bit 5 = ch 37 (r_lld_adv_start writes
        //                      the host's adv_channel_map << 5)
        //   CS+0x16            HOPCNTL = 0x8027: FH_EN with CH_IDX 39, so the sequence starts
        //                      at the channel after 39 and walks 37 -> 38 -> 39
        //   register 0x120     bits 15:0, µs between the starts of consecutive ADV packets
        //                      (r_lld_core_init writes 0xFFFF02D9 -> 729 µs)
        //
        // Silicon spacing is 730-734 µs for the same register value. The event stays live
        // until the last channel has been sent, even past the scheduler's reservation.
        private void SendAdvOnChannel(byte[] pdu, List<int> channels, int index, ulong nominalHalfUs,
            ulong spacingHalfUs, ulong sequence, ulong eventEpoch)
        {
            if(sequence != advSequenceEpoch || eventEpoch != radioEventEpoch || !radioEventLive)
            {
                return; // the sequence was stopped (CONNECT_IND) or its event is gone
            }
            var nowHalfUs = NowHalfMicroseconds();
            // MODELED SIMPLIFICATION: when a SCAN_REQ/SCAN_RSP exchange (or a CONNECT_IND)
            // on the previous channel is still on air at the nominal instant, the next ADV
            // waits for it to end plus T_IFS. Silicon does delay the next channel after a scan
            // exchange, but the exact rule is not yet measured.
            var busyUntilHalfUs = Math.Max(txInFlightUntilHalfUs, rxInFlightUntilHalfUs);
            if(busyUntilHalfUs > nowHalfUs)
            {
                var resumeHalfUs = busyUntilHalfUs + TifsMicroseconds * 2;
                advSequenceUntilHalfUs = Math.Max(advSequenceUntilHalfUs,
                    resumeHalfUs + (ulong)(channels.Count - index) * spacingHalfUs);
                ScheduleAdvOnChannel(pdu, channels, index, resumeHalfUs, spacingHalfUs, sequence, eventEpoch);
                return;
            }
            currentChannel = channels[index];
            SendOnMedium(pdu);
            M5Trace($"adv TX type={pdu[0] & 0xF} ch={currentChannel} slot={radioEventSlot}");
            if(index + 1 < channels.Count)
            {
                var nextHalfUs = Math.Max(nominalHalfUs, nowHalfUs) + spacingHalfUs;
                ScheduleAdvOnChannel(pdu, channels, index + 1, nextHalfUs, spacingHalfUs, sequence, eventEpoch);
            }
        }

        private void ScheduleAdvOnChannel(byte[] pdu, List<int> channels, int index, ulong atHalfUs,
            ulong spacingHalfUs, ulong sequence, ulong eventEpoch)
        {
            var nowHalfUs = NowHalfMicroseconds();
            var ts = machine.LocalTimeSource;
            var when = LocalDelay(atHalfUs > nowHalfUs ? atHalfUs - nowHalfUs : 0);
            ts.ExecuteInSyncedState(_ => SendAdvOnChannel(pdu, channels, index, atHalfUs, spacingHalfUs, sequence, eventEpoch), when);
        }

        private List<int> AdvChannelSequence(ulong cs)
        {
            var hopControl = sysbus.ReadWord(cs + CsHopControlOffset);
            var channelIndex = hopControl & HopChannelIndexMask;
            if((hopControl & HopFrequencyHopEnableBit) == 0)
            {
                return new List<int> { channelIndex };
            }
            var map = (sysbus.ReadWord(cs + CsAdvChannelMapOffset) >> CsAdvChannelMapShift) & 0x7;
            var sequence = new List<int>();
            for(var step = 1; step <= 3; step++)
            {
                var channel = AdvChannel37 + ((channelIndex - AdvChannel37 + step) % 3 + 3) % 3;
                if((map & (1 << (channel - AdvChannel37))) != 0)
                {
                    sequence.Add(channel);
                }
            }
            return sequence;
        }

        private ulong AdvPacketSpacingMicroseconds()
        {
            windowStorage.TryGetValue(AdvPacketIntervalRegisterOffset, out var value);
            return value & 0xFFFF;
        }

        // Assemble the over-the-air advertising-channel PDU from the control structure the
        // LL programmed in exchange memory (verified live): CS is EM segment index 1, with
        // the adv Access Address at CS+12 and the own BD_ADDR at CS+6/+8/+10. Advertising is
        // considered "on" only once the CS carries the adv-channel AA (0x8E89BED6); before
        // that (early init / non-adv) we emit nothing. This builds the raw channel PDU —
        // header{type,flags},{length} + AdvA[6] + AdvData; SendOnMedium adds the access
        // address that a BLEMedium frame carries in front of it.
        private byte[] BuildAdvPdu()
        {
            if(!TryResolveArmedControlStructure(out var csBase, out _))
            {
                return null;
            }
            if(sysbus.ReadDoubleWord(csBase + CsAccessAddressOffset) != AdvAccessAddress)
            {
                return null; // adv not programmed yet
            }

            // TX descriptor walk (M4, dumped live from the LL-programmed EM): CS+0x1c holds
            // the EM offset of a linked TX-descriptor ring (14-byte nodes: +0 next-desc EM
            // offset, +2 TXPHADV halfword, +4 TXDATAPTR EM offset of the AdvData buffer).
            // TXPHADV *is* the OTA header: byte0 = type[3:0]|txadd(6)|rxadd(7), byte1 =
            // advlen (AdvA + AdvData). The adv event transmits the first descriptor; the
            // SCAN_RSP descriptor in the same ring is transmitted by HandleScanRequest.
            // Only adv-type descriptors are event-start transmissions. A scanner's ring
            // head is its SCAN_REQ (type 3) and an initiator's is its CONNECT_IND (type 5)
            // — those are T_IFS responses, never broadcast (an ungated ring-head TX had the
            // initiator spraying CONNECT_IND every event, M5 fault-loop).
            foreach(var pduType in AdvTxPduTypes)
            {
                var desc = FindTxDesc(csBase, pduType);
                if(desc != 0)
                {
                    return BuildPduFromDesc(csBase, desc);
                }
            }
            return null;
        }

        // Assemble the OTA PDU for one TX descriptor: header from TXPHADV, AdvA from the
        // CS BD_ADDR (HW inserts it; it is NOT in the data buffer), payload from TXDATAPTR.
        private byte[] BuildPduFromDesc(ulong csBase, ulong desc)
        {
            var txPhAdv = sysbus.ReadWord(desc + 2);
            var header0 = (byte)txPhAdv;
            var advLen = (byte)(txPhAdv >> 8);
            if(advLen < 6)
            {
                return null; // not a legacy adv PDU (AdvA alone is 6 bytes)
            }

            var pdu = new byte[2 + advLen];
            pdu[0] = header0;
            pdu[1] = advLen;
            // AdvA[6] = own BD_ADDR, little-endian, at CS+6/+8/+10; the HW inserts it from
            // the CS, it is NOT part of the TXDATAPTR buffer. (In-sim this is base MAC+2 =
            // 00:00:00:00:00:02 since the eFuse MAC reads as zeros — verified live.)
            for(var i = 0; i < 6; i++)
            {
                pdu[2 + i] = sysbus.ReadByte(csBase + CsBdAddr0Offset + (ulong)i);
            }
            // AdvData (advlen - 6 bytes) from the TXDATAPTR buffer (dumped live: exactly the
            // HCI-set adv data, e.g. 02 01 06 0e 09 "ESP-BLE-HELLO").
            var dataLen = advLen - 6;
            if(dataLen > 0)
            {
                var dataPtr = ResolveEmOffset(sysbus.ReadWord(desc + 4));
                for(var i = 0; i < dataLen; i++)
                {
                    pdu[8 + i] = sysbus.ReadByte(dataPtr + (ulong)i);
                }
            }
            return pdu;
        }

        // Walk the CS TX-descriptor ring for the first descriptor of the wanted PDU type
        // (TXPHADV low nibble). The ring is circular (dumped live: 0x1400 -> 0x140e ->
        // 0x1400), so cap the walk. Returns 0 if absent — e.g. a passive scanner's LL
        // programs no SCAN_REQ descriptor, which is exactly the active-vs-passive signal.
        private ulong FindTxDesc(ulong csBase, int pduType)
        {
            var offset = sysbus.ReadWord(csBase + CsTxDescPtrOffset);
            for(var hop = 0; hop < 4 && offset != 0; hop++)
            {
                var desc = ResolveEmOffset(offset);
                if((sysbus.ReadWord(desc + 2) & 0xF) == pduType)
                {
                    return desc;
                }
                offset = (ushort)(sysbus.ReadWord(desc) & 0x7FFF); // bits0..14 = next-desc EM offset
            }
            return 0;
        }

        // --- M4c: SCAN_REQ / SCAN_RSP exchange (silicon-pinned: on real boards ~43% of an
        // active scanner's reports are evt_type=4 SCAN_RSP; see M3 doc §9) -----------------

        // RxAdd (header bit 7) of a SCAN_REQ / CONNECT_IND is the ADVERTISER's address type,
        // which the HW takes from the advertisement it is answering (TxAdd, bit 6) — the LL
        // cannot put it in the descriptor, because the same descriptor answers advertisers of
        // both address types. Without this the PDU claims a public AdvA, and any advertiser
        // using a random address discards it (BT Core Vol 6 Part B §2.3.1.4: the advertiser
        // responds only when AdvA *and* its type match): a random-address peer such as a
        // Zephyr/SoftDevice node then never sends SCAN_RSP, and an active scanner's host
        // stack sits waiting for a scan response that cannot arrive.
        private static byte AdvAddressTypeBit(byte[] advPdu)
        {
            return (byte)((advPdu[0] & AdvTxAddBit) << 1);
        }

        // Scanner side: after delivering a scannable adv PDU (ADV_IND=0 / ADV_SCAN_IND=6),
        // the RW HW autonomously transmits SCAN_REQ {ScanA=own BD_ADDR, AdvA=received} on
        // the same channel after T_IFS. Only when the LL programmed a SCAN_REQ descriptor
        // (active scan; TXPHADV 0x0c03 dumped live) — passive scan has none.
        private void TrySendScanRequest(byte[] advPdu)
        {
            if(!TryResolveArmedControlStructure(out var csBase, out _))
            {
                return;
            }
            var reqDesc = FindTxDesc(csBase, ScanReqPduType);
            if(reqDesc == 0)
            {
                return; // passive scan
            }
            var txPhAdv = sysbus.ReadWord(reqDesc + 2);
            var pdu = new byte[14];
            pdu[0] = (byte)(txPhAdv | AdvAddressTypeBit(advPdu));
            pdu[1] = 12;
            for(var i = 0; i < 6; i++)
            {
                pdu[2 + i] = sysbus.ReadByte(csBase + CsBdAddr0Offset + (ulong)i); // ScanA
                pdu[8 + i] = advPdu[2 + i];                                        // AdvA
            }
            ScheduleFrameSend(pdu, TifsAfter(advPdu));
            // Same commitment as the CONNECT_IND path, and for the same reason: the
            // sequencer owes this SCAN_REQ from the moment the ADV_IND passes filtering,
            // and the SCAN_RSP it obliges the advertiser to send arrives a further T_IFS
            // after it. Ending the event at its programmed duration transmitted the
            // SCAN_REQ into a dead event (measured: event END at 120320 us, SCAN_REQ on
            // air at 120430 us) and left the receiver closed when the answer came back,
            // so no scan response was ever reported -- which an active scanner that
            // withholds a device until its scan response arrives reads as "no device".
            // The hold runs to the end of the longest legacy adv-channel response, from
            // the spec's 37-octet payload maximum, not to any measured reply.
            var scanReqAirUs = AirTimeMicroseconds(pdu, ActivePhyRate);
            var holdUntil = NowHalfMicroseconds()
                + (TifsAfter(advPdu) + scanReqAirUs + TifsMicroseconds
                    + AirTimeMicroseconds(new byte[MaxAdvChannelPduLength], ActivePhyRate)) * 2;
            if(holdUntil > txInFlightUntilHalfUs)
            {
                txInFlightUntilHalfUs = holdUntil;
            }
        }

        // M5 initiator side: after delivering a connectable ADV_IND, an initiating LL has a
        // CONNECT_IND (type 5) TX descriptor in the CS ring; the HW autonomously transmits
        // CONNECT_IND {InitA=own BD_ADDR, AdvA=received, LLData} at T_IFS. The 22-byte LLData
        // is the packed struct r_lld_init_connect_req_pack (ROM 0x4001eb72) wrote into the
        // descriptor's data buffer; InitA/AdvA are HW-inserted (not in the buffer), same
        // contract as SCAN_REQ. Returns false when no CONNECT_IND descriptor is programmed
        // (plain scanner) so the caller falls back to SCAN_REQ.
        private bool TrySendConnectInd(byte[] advPdu)
        {
            // The initiating activity has its own control structure: a node that scans and
            // then connects runs scan as activity 0 and init as activity 1, and only the
            // init CS carries the CONNECT_IND TX-descriptor ring (verified live on stock
            // ESP-IDF blecent: CS#0 at 0x3fca1038 has CS+0x1c = 0, CS#1 at 0x3fca1092 has
            // 0x147e). Reading activity 0 unconditionally found no type-5 descriptor, so
            // the initiator never answered an ADV_IND and no connection was ever formed.
            if(!TryResolveArmedControlStructure(out var csBase, out _))
            {
                return false;
            }
            if(FindTxDesc(csBase, ConnectIndPduType) == 0)
            {
                return false;
            }
            // Real RW hardware fetches the CONNECT_IND descriptor when the transmitter
            // pulls the bytes -- one T_IFS after the ADV_IND ends -- not when the ADV_IND
            // lands. That gap is the only window the link layer has to patch the LLData
            // for this particular reception: WinOffset is computed from the ADV_IND's own
            // arrival time, so it cannot have been packed in advance. Assembling the PDU
            // here, in the same instant the frame is delivered, transmitted whatever the
            // buffer held before the RX-done ISR had run a single instruction -- and that
            // is WinOffset=0, against the 31 a real C3 initiator sends (measured on two
            // devkits, see open-source/e-ink/hil-c3ble).
            var ts = machine.LocalTimeSource;
            var sendAt = LocalDelayMicroseconds(TifsAfter(advPdu));
            ts.ExecuteInSyncedState(_ => SendConnectIndFromDescriptor(csBase, advPdu), sendAt);
            // The sequencer is committed to this response from the moment the ADV_IND
            // passes filtering: on silicon the event runs through the T_IFS turnaround
            // and the CONNECT_IND transmission before it can end. Hold the event's END
            // until then (see EndRadioEvent) -- an ADV_IND that lands near the window's
            // programmed edge otherwise has its event reaped mid-turnaround, the
            // CONNECT_IND goes out into a dead event, and the EOF path reads a
            // descriptor whose txdone has not landed yet.
            var connIndAirUs = AirTimeMicroseconds(new byte[ConnectIndPduLength], ActivePhyRate);
            var holdUntil = NowHalfMicroseconds()
                + (TifsAfter(advPdu) + connIndAirUs) * 2;
            if(holdUntil > txInFlightUntilHalfUs)
            {
                txInFlightUntilHalfUs = holdUntil;
            }
            // This node is now the master: subsequent event windows are connection events
            // and both peers follow the hop sequence. Master conn activity inherits the
            // initiating activity's index 0 (silicon conn handle 0x0000). The channel
            // switch happens just AFTER the scheduled CONNECT_IND send -- the medium reads
            // the sender's channel at send time and the slave still listens on 37.
            var roleAt = LocalDelayMicroseconds(TifsAfter(advPdu) + 10);
            ts.ExecuteInSyncedState(_ =>
            {
                connRole = ConnRole.Master;
                connActivityTag = 0;
                M5Trace("master role active");
            }, roleAt);
            return true;
        }

        // Fetch and transmit the CONNECT_IND at the instant the transmitter would, reading
        // the CS TX ring then rather than at ADV_IND time. Re-resolving the descriptor here
        // (not caching it from the caller) is the same contract: the hardware walks the ring
        // when it transmits.
        private void SendConnectIndFromDescriptor(ulong csBase, byte[] advPdu)
        {
            var desc = FindTxDesc(csBase, ConnectIndPduType);
            if(desc == 0)
            {
                return;
            }
            var txPhAdv = sysbus.ReadWord(desc + 2);
            var pdu = new byte[ConnectIndPduLength];
            pdu[0] = (byte)(txPhAdv | AdvAddressTypeBit(advPdu));
            pdu[1] = 34;
            for(var i = 0; i < 6; i++)
            {
                pdu[2 + i] = sysbus.ReadByte(csBase + CsBdAddr0Offset + (ulong)i); // InitA
                pdu[8 + i] = advPdu[2 + i];                                        // AdvA
            }
            var dataPtr = ResolveEmOffset(sysbus.ReadWord(desc + 4));
            for(var i = 0; i < 22; i++)
            {
                pdu[14 + i] = sysbus.ReadByte(dataPtr + (ulong)i);                 // LLData
            }
            // WinOffset is inserted by the hardware at transmit time, not carried in the
            // LLData buffer: the buffer is packed once when the initiating activity starts
            // and never rewritten (verified in sim -- the 22 bytes are byte-identical from
            // the ADV_IND through every later event end), yet a real C3 initiator puts a
            // different WinOffset on air for every connection (25, 27, 31, 32, 34 over five
            // runs on two devkits, read back from the peer's lld_con_env+0x60). It cannot be
            // pre-packed because it measures from the ADV_IND's own arrival time, and the
            // firmware cannot write it inside T_IFS. What the firmware does supply is
            // CS+0x1E, which holds exactly the offset its own anchor implies:
            // (master anchor 2080 - connind end 1956 - transmitWindowDelay 4) / 4 = 30.
            // Take that value rather than the stale buffer byte -- CS+0x20 (WinSize*4) and
            // CS+0x22 (Interval) sit beside it and match the LLData. See CsWinOffsetOffset
            // for why the silicon-verified CS+0x44 is the wrong field *at this moment*.
            //
            // The CS value is a seed, not the answer: real RW hardware MAINTAINS the
            // window offset as time passes, so reading it statically goes stale by the
            // gap between the LL's own reference and the actual transmit instant. The LL
            // computed it against this event's start rounded up to the 1.25 ms offset
            // grid; re-express that same anchor against where the CONNECT_IND actually
            // ends before putting it on air. The anchor is the firmware's -- only the
            // moment it is measured from changes.
            var winOffset = (ulong)sysbus.ReadWord(csBase + CsWinOffsetOffset);
            var csWinOffset = winOffset;
            var interval = (ulong)(pdu[ConnectIndLlDataOffset + 10]
                | (pdu[ConnectIndLlDataOffset + 11] << 8));
            if(interval != 0)
            {
                var refHalfUs = (radioEventStartHalfUs + ConnUnitHalfMicroseconds - 1)
                    / ConnUnitHalfMicroseconds * ConnUnitHalfMicroseconds;
                var intervalHalfUs = interval * ConnUnitHalfMicroseconds;
                // The master's anchor is not ours to estimate: the LL computes it in
                // r_lld_init_process_pkt_tx_cal_con_timestamp (ROM 0x4001e01e, blob
                // lld_init.o) from fields it has already written, and every one of them is
                // readable here. Run the ROM's own arithmetic instead of a stand-in:
                //
                //   anchor = ref54 + interval - ((ref54 - 2*rec[4]) mod interval)
                //
                // rec[4] is 0 on this part (see the initrec dump below), so this is
                // "round ref54 up to the next interval grid point".
                //
                // There was a second line here, a deferral gated on 4 * CS[0x44], and it
                // was wrong. CS+0x44 is the WinOffset of an ESTABLISHED connection -- see
                // CsWinOffsetOffset, where that is recorded against the sniffer 5/5 -- and
                // this call site runs at CONNECT_IND TX, when the connection does not exist
                // yet. Probed here at that instant, the armed control structure still holds
                // the ADVERTISING access address 0x8E89BED6 and CS+0x44 reads 0: 42/42
                // blecent-cycle CONNECT_INDs and every CrossPoint one, matching the 5123
                // already recorded on the other constant. On silicon it holds the previous
                // attempt's value, so it is stale rather than merely empty.
                //
                // The units give it away. 1.25 ms is 4 half-slots, so `4 * CS[0x44]` is a
                // WinOffset converted to half-slots -- the deferral was comparing this
                // connection's anchor gap against some earlier connection's window offset.
                // It also could not discriminate: the gap is
                // `interval - (ref54 mod interval)`, at most `intervalSlots` (96 at a 30 ms
                // interval), while the threshold when populated was 108 or 116. Whenever
                // the field was non-zero the branch was taken unconditionally, which is the
                // "always defer" already recorded here as taking blecent from 42/42 to
                // 5/13.
                //
                // CONFIRMED ON SILICON 2026-08-21, and it could have come out otherwise.
                // hil/nrf-ble-link-oracle/winoff_capture.py measures, over the air on the
                // sniffer's single clock,
                //
                //   start(central's 1st connection-event packet) - end(CONNECT_IND)
                //
                // against the WinSize/WinOffset that same CONNECT_IND advertised.
                // 162 of 163 establishments landed INSIDE the advertised window, residual
                // over `transmitWindowDelay + WinOffset` within the 2500 us WinSize budget.
                // WinOffset covered 0..23, all 24 values, so the entire phase range the
                // deferral claimed to react to was exercised.
                //
                // The one exception is worth stating rather than rounding away: conn 54
                // came in at +30881 us = 1.029 x connInterval. That is one interval, not
                // two. A deferral is a TWO-interval signature (~60 ms residual), and it
                // would be deterministic in phase -- yet conn 56, one WinOffset away, was
                // in window. One sample in 163 at exactly +1 interval is a missed capture,
                // the same artifact EXP-anchor-grid run 1 recorded ("a single 60.001 = a
                // missed event"). Under S4.5.5 the peer simply takes the next transmit
                // window, which is what the recorded packet is.
                //
                // What this replaces was an estimate built from CS+0x1E, right only when
                // the ADV_IND happened to land near the end of an interval. When it landed
                // early the estimate named a grid point the LL had already passed over, so
                // the CONNECT_IND advertised a window one interval before the one the
                // central actually used -- and the peer, doing what §4.5.5 requires of an
                // empty window, stepped its channel while the central kept event 0's. Same
                // firmware, same peer, two reconnects in a row: one live link, one deaf.
                var anchorHalfUs = refHalfUs + TransmitWindowDelayHalfUs
                    + winOffset * ConnUnitHalfMicroseconds;
                var initEnv = sysbus.ReadDoubleWord(lldInitEnv);
                if(initEnv >= 0x3fc00000 && initEnv < 0x3fd00000 && intervalHalfUs > 0)
                {
                    var refSlots = (ulong)sysbus.ReadDoubleWord(initEnv + 0x54);
                    var intervalSlots = intervalHalfUs / HalfSlotHalfMicroseconds;
                    // rec[4]: the offset the LL planned to keep a new link off existing ones
                    // (0 with no other link). rec = init_env + co_rate_to_phy[init_env+0x4e]*10.
                    var rate = sysbus.ReadByte(initEnv + 0x4e);
                    var phy = sysbus.ReadByte(coRateToPhy + rate);
                    var planSlots = 2 * (ulong)sysbus.ReadWord(initEnv + (ulong)phy * 10 + 4);
                    var phase = (long)((refSlots + intervalSlots * 4 - planSlots % intervalSlots) % intervalSlots);
                    var anchorSlots = refSlots + intervalSlots - (ulong)phase;
                    anchorHalfUs = anchorSlots * HalfSlotHalfMicroseconds;
                    M5Trace($"connind rom: ref54={refSlots} ivslots={intervalSlots} plan={planSlots} "
                        + $"anchorSlots={anchorSlots} anchor={anchorHalfUs / 2}us");
                }
                else
                {
                    M5Trace($"connind rom: SKIPPED initEnv=0x{initEnv:X} iv={intervalHalfUs}");
                }
                // Where the peer will start measuring: the end of this packet, plus the
                // delay §4.5.3 puts before the window regardless of WinOffset.
                var windowRefHalfUs = TransmitWindowDelayHalfUs + NowHalfMicroseconds()
                    + AirTimeMicroseconds(pdu, ActivePhyRate) * 2;
                // WinOffset is just the LL's own anchor restated against the moment the
                // peer starts measuring from -- the end of this packet plus the
                // transmitWindowDelay §4.5.3 imposes regardless of WinOffset.
                //
                // Only two adjustments are legitimate. The anchor was computed against
                // this radio event's start, so it can already be in the past by the time
                // the packet is on air; the grid is periodic, so stepping forward by whole
                // intervals names the same anchor. And §2.3.3.1 caps WinOffset at
                // connInterval, so anything above that is clamped -- the leftover is
                // sub-unit slop between the LL's 1.25 ms grid and the real end of this
                // packet, which is precisely what the transmit window (WinSize) absorbs.
                //
                // An earlier revision added a whole interval here before reducing modulo
                // the interval. On a connection whose anchor was genuinely one interval
                // ahead -- the C3's own establishment deferral -- that reduced twice and
                // advertised WinOffset=0, pointing the peer at a window the central never
                // used. The peer then did what §4.5.5 requires of an empty window (count
                // it, step the channel), the central kept evtcnt=0 and its first hop, and
                // the two ran the same CSA#1 list one step apart: deaf from event one,
                // both ends believing themselves healthy.
                var deltaHalfUs = (long)anchorHalfUs - (long)windowRefHalfUs;
                while(deltaHalfUs < 0)
                {
                    deltaHalfUs += (long)intervalHalfUs;
                }
                var leadHalfUs = (ulong)deltaHalfUs;
                winOffset = leadHalfUs / ConnUnitHalfMicroseconds;
                if(winOffset > interval)
                {
                    winOffset = interval;
                }
                M5Trace($"connind winoff: cs={csWinOffset} evtStart={radioEventStartHalfUs / 2}us "
                    + $"ref={refHalfUs / 2}us anchor={anchorHalfUs / 2}us "
                    + $"windowRef={windowRefHalfUs / 2}us lead={leadHalfUs / 2}us -> {winOffset}");
                // §4.5.4 is a "shall": the Central shall start to send the first packet
                // WITHIN the transmit window (only its tail may extend past). If the
                // clamp above threw away more than WinSize can absorb, this CONNECT_IND
                // points a peripheral at a window the central will not transmit in, and a
                // peer that honours WinSize -- as a real one does, and as ScriptedBlePeer
                // does not yet (BLE_spec/MODEL_GAPS.md E2b) -- will miss the whole event
                // and step its channel per §4.5.5. Say so rather than let a green bench
                // that only proves our own peer is permissive stand as conformance.
                var windowStartHalfUs = windowRefHalfUs + winOffset * ConnUnitHalfMicroseconds;
                var winSizeHalfUs = (ulong)pdu[ConnectIndLlDataOffset + 7] * ConnUnitHalfMicroseconds;
                var firstPacketHalfUs = anchorHalfUs + TransmitWindowDelayHalfUs;
                if(firstPacketHalfUs > windowStartHalfUs + winSizeHalfUs)
                {
                    this.Log(LogLevel.Warning,
                        "CONNECT_IND advertises a transmit window this connection will not "
                        + "transmit in: window {0}us..{1}us, first packet {2}us "
                        + "({3}us late, WinOffset capped at connInterval per §2.3.3.1). "
                        + "A peripheral honouring WinSize would miss connection event 0.",
                        windowStartHalfUs / 2, (windowStartHalfUs + winSizeHalfUs) / 2,
                        firstPacketHalfUs / 2,
                        (firstPacketHalfUs - windowStartHalfUs - winSizeHalfUs) / 2);
                }
            }
            pdu[ConnectIndLlDataOffset + 8] = (byte)winOffset;
            pdu[ConnectIndLlDataOffset + 9] = (byte)(winOffset >> 8);
            connectIndDataPtr = dataPtr;
            if(tracePath != null)
            {
                // The LLData buffer never carries a WinOffset in sim, yet silicon puts a
                // per-reception one on air (25..34 over five HIL runs). If the hardware
                // inserts it at TX time, the value it inserts has to come from a field the
                // firmware programmed into the initiating activity's control structure.
                // Dump the whole CS so that field can be identified rather than guessed.
                var cs = new System.Text.StringBuilder();
                for(var i = 0; i < 0x5A; i += 2)
                {
                    cs.Append($"{i:X2}:{sysbus.ReadWord(csBase + (ulong)i):X4} ");
                }
                M5Trace($"init CS @0x{csBase:X} {cs}");
                // r_lld_init_process_pkt_tx_cal_con_timestamp (ROM 0x4001e01e, blob
                // lld_init.o) computes the master's first anchor entirely from these:
                //   rec    = init_env + co_rate_to_phy[init_env+0x4e]*10
                //   anchor = ref54 + rec[2]*4 - ((ref54 - 2*rec[4]) mod (rec[2]*4))
                //   if ((anchor - ref54) < CS[0x44]*4) anchor += rec[2]*4
                // Everything but rec[4] is already known to match silicon, and rec[4]==0
                // reproduces the 5-half-slot-early anchor exactly. Dump the record.
                var ie = sysbus.ReadDoubleWord(lldInitEnv);
                if(ie >= 0x3fc00000 && ie < 0x3fd00000)
                {
                    var rate = sysbus.ReadByte(ie + 0x4e);
                    var phy = sysbus.ReadByte(coRateToPhy + rate);
                    var rec = ie + (ulong)phy * 10;
                    var dump = new System.Text.StringBuilder();
                    for(var i = 0; i < 10; i += 2)
                    {
                        dump.Append($"{i:X2}:{sysbus.ReadWord(rec + (ulong)i):X4} ");
                    }
                    M5Trace($"init ENV ptr=0x{ie:X} rate={rate} phy={phy} rec=0x{rec:X} {dump}"
                        + $"ref54={sysbus.ReadDoubleWord(ie + 0x54)}"
                        + $" cs44={sysbus.ReadWord(csBase + 0x44)}");
                }
            }
            M5Trace($"connind lldata dataPtr=0x{dataPtr:X} bytes="
                + BitConverter.ToString(pdu, 14, 22)
                + $" | AA=0x{pdu[14] | (pdu[15] << 8) | (pdu[16] << 16) | (pdu[17] << 24):X8}"
                + $" CRCInit=0x{pdu[18] | (pdu[19] << 8) | (pdu[20] << 16):X6}"
                + $" WinSize={pdu[21]} WinOffset={pdu[22] | (pdu[23] << 8)}"
                + $" Interval={pdu[24] | (pdu[25] << 8)} Latency={pdu[26] | (pdu[27] << 8)}"
                + $" Timeout={pdu[28] | (pdu[29] << 8)} HopSca=0x{pdu[35]:X2}");
            // Both peers address the connection with the AA carried in this LLData, so
            // capture it before the role switch makes it the medium prefix.
            connAccessAddress = ReadConnectIndAccessAddress(pdu);
            // Already at T_IFS: this call IS the transmission instant.
            SendOnMedium(pdu);
            M5Trace($"CONNECT_IND sent (LLData @0x{dataPtr:X})");
            firstConnEventTxPending = true;
            // A new connection re-derives its own deferral; carrying the previous link's
            // over would shift this one's grid before its establishment event ran.
            connSlotDeferralHalfUs = 0;

            // txdone (word0 bit15) means the transmitter finished putting the packet on
            // air, so it belongs one packet duration after transmission starts, not at
            // the same instant. The link layer computes the connection anchor from this
            // signal, and whether the anchor it wants is still reachable is a threshold
            // test: raising txdone a packet early hands the firmware ~350 us of lead time
            // the silicon never gives it, which is enough to flip that test and place the
            // first connection event a whole interval earlier than the peer expects.
            //
            // Measured against two devkits (see open-source/e-ink/hil-c3ble): silicon
            // defers by one interval on every connection and both roles, so the anchor
            // sits interval - 2 half-slots past the sync point. This is deliberately not
            // modelled by forcing that outcome -- the deferral is the firmware's own
            // decision, and a different link layer (an open-source controller, another
            // vendor's) is entitled to decide differently from the same signal. What the
            // model owes it is the signal at the right time.
            var eof = new TimeStamp(
                machine.LocalTimeSource.ElapsedVirtualTime
                    + TimeInterval.FromMicroseconds(AirTimeMicroseconds(pdu, ActivePhyRate)),
                machine.LocalTimeSource.Domain);
            machine.LocalTimeSource.ExecuteInSyncedState(
                _ => sysbus.WriteWord(desc, (ushort)(sysbus.ReadWord(desc) | 0x8000)), eof);
        }

        // False only while initiating toward a named peer that this ADV_IND is not from.
        private bool IsInitiatorTarget(byte[] advInd, ulong csBase)
        {
            if(advInd.Length < 8 || csBase == 0 || FindTxDesc(csBase, ConnectIndPduType) == 0)
            {
                return true;
            }
            var named = false;
            var match = true;
            for(var i = 0; i < 6; i++)
            {
                var peer = sysbus.ReadByte(csBase + CsInitPeerAddr0Offset + (ulong)i);
                named |= peer != 0;
                match &= advInd[2 + i] == peer;
            }
            return !named || match;
        }

        // Advertiser side: SCAN_REQ is consumed by the HW itself (never surfaces as an RX
        // descriptor to the LL); if it addresses our AdvA while advertising, the HW sends
        // the SCAN_RSP descriptor from the CS TX ring after T_IFS.
        private void HandleScanRequest(byte[] req)
        {
            if(!TryResolveArmedControlStructure(out var csBase, out _)
                || sysbus.ReadDoubleWord(csBase + CsAccessAddressOffset) != AdvAccessAddress)
            {
                return;
            }
            for(var i = 0; i < 6; i++)
            {
                if(req[8 + i] != sysbus.ReadByte(csBase + CsBdAddr0Offset + (ulong)i))
                {
                    return; // not addressed to us
                }
            }
            var rspDesc = FindTxDesc(csBase, ScanRspPduType);
            if(rspDesc == 0)
            {
                return;
            }
            var pdu = BuildPduFromDesc(csBase, rspDesc);
            if(pdu != null)
            {
                var delayMicroseconds = TifsAfter(req);
                // The radio is committed to the answer from here: nothing else (the next
                // advertising channel) may start before it is off the air.
                var holdUntil = NowHalfMicroseconds() + (delayMicroseconds + AirTimeMicroseconds(pdu, ActivePhyRate)) * 2;
                if(holdUntil > txInFlightUntilHalfUs)
                {
                    txInFlightUntilHalfUs = holdUntil;
                }
                ScheduleFrameSend(pdu, delayMicroseconds);
            }
        }

        // --- M5: connection-event data exchange --------------------------------
        // Each connection event: the master transmits first (empty data PDU LLID=1 when it
        // has no data — real RW HW generates these autonomously), the slave answers at
        // T_IFS. Both deliveries go through the standard tracked-window RX path with the
        // connection activity's tag so r_lld_rxdesc_check accepts them for lld_con.
        private void HandleConnData(byte[] frame)
        {
            var header = frame[0];
            // Deliver ONLY into an armed CONNECTION-event slot (sch_prog TYPE 31 = first/
            // establishment event, TYPE 14 = steady state; dumped live). A data PDU pushed
            // into a lingering ADV slot (TYPE 5) reads as a malformed ADV_DIRECT_IND and
            // wedges the adv frm processing — the M5 slave-wedge fault. A miss is benign:
            // the master retransmits every event and a conn window catches one.
            // Decrypt before delivery: on real HW the CCM engine sits between the demodulator
            // and the RX buffer, so the link layer only ever sees plaintext (plus a status
            // bit when authentication failed).
            // The event armed in the scheduler owns this reception, and its slot names the
            // control structure it serves — so the activity tag the LL expects in the RX
            // descriptor comes from the slot, not from tracked state or a priority match.
            if(IsRxGateOpen() && TryResolveArmedControlStructure(out _, out var rxActId))
            {
                // M6: run the LL acknowledgement state machine on the received header's
                // SN/NESN (BT Core Vol 6 Part B §5.1.3). Without this the LL never sees its
                // real LLCP PDUs acked, so it retransmits forever and never starts the next
                // procedure — LL_VERSION_IND was never queued behind the acked
                // LL_FEATURE_REQ.
                //
                // This belongs INSIDE the delivery gate. The ARQ state machine lives in the
                // MAC receiver, downstream of the demodulator: a frame that arrived while
                // this node's radio was not in an armed connection event was never received
                // at all, so it can neither advance SN/NESN nor acknowledge our last
                // transmission. Running it unconditionally made the model confirm a TX
                // descriptor whose PDU the peer had discarded — the sender then believed an
                // unheard LLCP request had been answered and waited forever for a reply the
                // peer never generated. Retransmission needs no code: the descriptor stays
                // unconfirmed, so the next event refetches the same one.
                txConfirmedByRx = false;
                consecutiveCrcErrors = 0;
                ProcessSeq(header);
                lastConnRxHeader = header;

                // Decrypt inside the gate too, and for the same reason: the CCM engine sits
                // between the demodulator and the RX buffer, so it only ever runs on a frame
                // the receiver actually accepted. It also needs the armed slot, since that is
                // now what names the control structure holding the session key.
                var micError = false;
                frame = DecryptConnPdu(frame, out micError);

                var rxCtrl = sysbus.ReadWord(radioEventCtrlAddr);
                sysbus.WriteWord(radioEventCtrlAddr, (ushort)((rxCtrl & ~SchProgTypeMask) | (2 << 3)));
                FillRxDescriptor(frame, rxActId, micError);
                RaiseStatusBit(RxDoneBit);
                // TX done is the descriptor's txdone, set by the NESN in this header, so it
                // is raised together with this RX done.
                if(txConfirmedByRx)
                {
                    txConfirmedByRx = false;
                    RaiseStatusBit(TxDoneBit);
                }
                M5Trace($"conn data delivered (len={frame.Length}, slot={radioEventSlot} act={rxActId} ctrl=0x{rxCtrl:X4})");

                // The slave answers the master's packet at T_IFS, and only when it actually
                // heard one: a slave whose radio was not in this event transmits nothing, so
                // this is gated with the reception rather than run unconditionally. Pending
                // TX descriptors (LLCP responses like LL_VERSION_IND) take the slot; else an
                // empty PDU.
                if(connRole == ConnRole.Slave)
                {
                    ScheduleConnFrameSend(BuildConnTxPdu(), TifsAfter(frame));
                }
                else if(connRole == ConnRole.Master && ShouldContinueConnEvent(header))
                {
                    ContinueConnEvent(TifsAfter(frame), radioEventEpoch);
                }
            }
            else
            {
                M5Trace($"conn data DROPPED (evtLive={radioEventLive}, slot={radioEventSlot})");
            }
        }

        // Assemble this event's outgoing data PDU: a pending TX descriptor if the LL queued
        // one, else the empty PDU real RW hardware generates autonomously. Sequence bits are
        // stamped first and encryption applied last, matching the hardware order (the packet
        // formatter inserts SN/NESN, then the CCM engine seals the payload).
        private byte[] BuildConnTxPdu()
        {
            return EncryptConnPdu(StampSeq(TryFetchConnTxPdu() ?? EmptyDataPdu));
        }

        // Stamp the LL sequence bits (SN=bit3, NESN=bit2) into a conn-PDU header from the
        // model's per-connection state, preserving LLID[1:0] and MD[4]. On real HW these
        // are HW-inserted at TX time (not stored in the descriptor), so overwriting a
        // fetched descriptor's bits here is faithful. Returns a fresh copy.
        private byte[] StampSeq(byte[] pdu)
        {
            var copy = (byte[])pdu.Clone();
            copy[0] = (byte)((copy[0] & ~0x0C) | (connSn << 3) | (connNesn << 2));
            return copy;
        }

        // Advance the model's SN/NESN from a received header (§5.1.3): if the peer's NESN
        // differs from our SN our last TX was acked (advance SN); if the peer's SN matches
        // our NESN it carried new data (flip NESN to ack). The deterministic medium never
        // drops, so no retransmit path is needed.
        private void ProcessSeq(byte header)
        {
            var peerSn = (header >> 3) & 1;
            var peerNesn = (header >> 2) & 1;
            if(peerNesn != connSn)
            {
                connSn ^= 1;
                ConfirmConnTx();
            }
            if(peerSn == connNesn)
            {
                connNesn ^= 1;
            }
        }

        // The peer's NESN flipped, so our last transmission was acknowledged. That is the
        // instant the MAC marks the TX descriptor done and raises TX done, and it is the
        // whole of the link layer's acknowledgement evidence:
        //
        //   descriptor word0 bit15 -> INTSTAT bit 1 -> r_lld_con_tx_isr (0x4001b47e)
        //     -> r_lld_con_tx (0x4001a394) reclaim loop
        //        LLID==3 -> ke_msg 0x20c -> lld_llcp_tx_cfm_handler (0x4001110c)
        //        LLID 1/2 -> ke_msg 0x20e -> lld_acl_tx_cfm_handler  (0x4001057a)
        //     -> clears bit 0x0002 of llc_env[link]+0x42
        //     -> r_llc_llcp_tx_check (0x40010dd2) may hand over the NEXT LLCP PDU
        //
        // r_llc_llcp_tx_check sets that same latch immediately before dispatching a
        // control PDU and its entire queue walk is guarded on it being clear, so a
        // controller that transmits one LLCP PDU and never confirms it can never send a
        // second: the version/feature exchange stalls and the host, which defers
        // BLE_GAP_EVENT_CONNECT behind it, never reports the connection.
        //
        // An empty PDU carries no descriptor, so there is nothing to confirm for it.
        private void ConfirmConnTx()
        {
            if(pendingTxDesc == 0)
            {
                return;
            }
            var word0 = sysbus.ReadWord(pendingTxDesc);
            sysbus.WriteWord(pendingTxDesc, (ushort)(word0 | 0x8000));
            // The ring's current-descriptor pointer is the hardware's, not the link
            // layer's: r_lld_con_start writes CS+0x1c once, to the first slot, and
            // r_lld_con_tx_prog_new_packet only ever fills the next free slot and chains
            // it (the last slot's NEXTPTR points back at the first). Nothing in the ROM
            // rewrites CS+0x1c afterwards, so a pointer left at the first slot puts the
            // newest PDU ahead of an older one sitting in the second slot as soon as the
            // ring wraps -- observed as the slave's SMP key-distribution ACL going on air
            // before its LL_START_ENC_RSP, which makes the central drop the link. Advance
            // the pointer to the acked descriptor's NEXTPTR, as the MAC does.
            sysbus.WriteWord(pendingTxCs + CsTxDescPtrOffset, (ushort)(word0 & 0x7FFF));
            pendingTxDesc = 0;
            txConfirmedByRx = true;
            // The descriptor is now free for the LL to refill with a different, later PDU
            // (it is a ring slot, not a one-shot buffer) -- drop the cached ciphertext with
            // it so a future reuse of this same address can never read back as a cache hit
            // for the wrong PDU.
            txCipherDesc = 0;
            txCipherPayload = null;
        }

        // Which connection control structure is this event's? The running scheduler slot
        // already names it -- SchProgCsPtrOffset holds the CS's own EM offset, and
        // TryResolveArmedControlStructure turns that into the link id. Deriving it from a
        // role-dependent constant instead gets the master wrong: the slave's connection
        // activity happens to land on link 1 and the master's on link 1 too, but the model
        // was assuming 1 and 0 respectively, so the master resolved link 0's control
        // structure, read a TX ring head of 0, and never found the descriptor its own link
        // layer had programmed. The slot is the firmware-supplied answer; use it.
        private bool TryResolveConnControlStructure(out ulong cs)
        {
            if(TryResolveArmedControlStructure(out cs, out _))
            {
                return true;
            }
            cs = 0;
            return false;
        }

        // M6: fetch a pending TX descriptor from the CONNECTION control structure's ring.
        // Conn CS for link n = EM 0x400 + n*90 (r_lld_con_rx 0x4001a214 reads the event
        // counter at em(0x400 + link*90 + 80)); link id == connActivityTag (== HCI handle).
        // Ring pointer at CS+0x1c, same field as the adv CS. Empty-PDU events queue no
        // descriptor (HW auto-generates empties), so a pending descriptor = real data
        // (LLCP control or L2CAP). Descriptor: +0 next|txdone(bit15), +2 TXPHCE
        // (byte0 = LLID/NESN/SN/MD header, byte1 = payload length), +4 data-buffer EM
        // offset. Marks the descriptor txdone so the LL's event-end processing frees it.
        private byte[] TryFetchConnTxPdu()
        {
            if(!TryResolveConnControlStructure(out var cs))
            {
                return null;
            }
            var offset = sysbus.ReadWord(cs + CsTxDescPtrOffset);
            if(connTxRingTraced < 3)
            {
                connTxRingTraced++;
                M5Trace($"conn TX ring: role={connRole} cs=0x{cs:X} head=0x{offset:X4}");
            }
            if(tracePath != null)
            {
                var chain = new System.Text.StringBuilder();
                var o = offset;
                for(var hop = 0; hop < 8 && o != 0; hop++)
                {
                    var d = ResolveEmOffset(o);
                    var w0 = sysbus.ReadWord(d);
                    var ph = sysbus.ReadWord(d + 2);
                    chain.Append($" [0x{o:X4} w0=0x{w0:X4} ph=0x{ph:X4}]");
                    o = (ushort)(w0 & 0x7FFF);
                }
                M5Trace($"conn TX chain: role={connRole} head=0x{offset:X4}{chain}");
            }
            for(var hop = 0; hop < 4 && offset != 0; hop++)
            {
                var desc = ResolveEmOffset(offset);
                var word0 = sysbus.ReadWord(desc);
                if((word0 & 0x8000) == 0)
                {
                    var txPhCe = sysbus.ReadWord(desc + 2);
                    var len = (byte)(txPhCe >> 8);
                    var pdu = new byte[2 + len];
                    pdu[0] = (byte)txPhCe;
                    pdu[1] = len;
                    var dataPtr = ResolveEmOffset(sysbus.ReadWord(desc + 4));
                    for(var i = 0; i < len; i++)
                    {
                        pdu[2 + i] = sysbus.ReadByte(dataPtr + (ulong)i);
                    }
                    // Do NOT mark the descriptor done here. Word0 bit15 means
                    // ACKNOWLEDGED, not transmitted: r_lld_con_start initialises it SET
                    // (idle), r_lld_con_tx_prog_new_packet CLEARS it to hand the
                    // descriptor to the MAC, and no ROM path ever sets it again — so it
                    // is the hardware's to set, and only once the peer has acked. The
                    // link layer does no SN/NESN comparison of its own; this bit is its
                    // sole evidence, and setting it at transmit time both fakes an ack
                    // and skips the retransmission the descriptor is still eligible for.
                    // Remember it instead and confirm from ProcessSeq.
                    pendingTxDesc = desc;
                    pendingTxCs = cs;
                    M5Trace($"conn TX desc: hdr=0x{txPhCe:X4} len={len} pdu={BitConverter.ToString(pdu)}");
                    return pdu;
                }
                offset = (ushort)(word0 & 0x7FFF);
            }
            return null;
        }

        // --- Link-layer CCM ----------------------------------------------------
        // The RW-BLE core encrypts and decrypts connection data PDUs in hardware, driven
        // entirely from the connection's control structure in exchange memory — there are no
        // MMIO registers for it at all. Field offsets decoded from ROM r_lld_con_enc_key_load
        // (0x4001cc92), the only function that programs them, plus r_lld_con_rx_enc
        // (0x4001cbfc) / r_lld_con_tx_enc (0x4001cb66) for the enables:
        //   CS+2   bit8 = RX crypt enable, bit9 = TX crypt enable
        //   CS+44  session key, 16 octets, stored BYTE-REVERSED relative to the buffer the
        //          link layer passes (enc_key_load writes key[15-i] first)
        //   CS+60  IV, 8 octets, in order
        //   CS+68  TX packet counter, CS+74 RX packet counter (48-bit LE, 39 bits used)
        // enc_key_load zeroes both counters and nothing else in the ROM ever writes them, so
        // the hardware owns them — and therefore so does this model.
        //
        // The crypto itself is NOT reverse-engineered: it is the published AES-CCM of BT Core
        // Vol 6 Part E, implemented once in BleCcm and shared with the nRF model so the two
        // controllers cannot drift apart.
        private bool TryGetConnCrypt(out ConnCrypt crypt)
        {
            crypt = default(ConnCrypt);
            if(connRole == ConnRole.None)
            {
                return false;
            }
            // Same rule as the TX ring: the running scheduler slot names the control
            // structure this event serves, so read it from there rather than computing
            // 0x400 + connActivityTag*90. That constant is per-role and wrong for the
            // master — both roles carry this connection on link 1, so a master resolved
            // link 0 and would have loaded the stale initiating activity's key material.
            // Both callers run inside an armed connection event, so the slot is available.
            if(!TryResolveConnControlStructure(out var cs))
            {
                return false;
            }
            var control = sysbus.ReadWord(cs + CsTxRxControlOffset);
            if(connCryptCsTraced < 4)
            {
                connCryptCsTraced++;
                M5Trace($"conn crypt CS: role={connRole} cs=0x{cs:X} ctrl=0x{control:X4}");
            }
            crypt.RxEnabled = (control & CsRxCryptEnableBit) != 0;
            crypt.TxEnabled = (control & CsTxCryptEnableBit) != 0;
            if(!crypt.RxEnabled && !crypt.TxEnabled)
            {
                return false;
            }
            crypt.ControlStructure = cs;
            crypt.Key = new byte[BleCcm.KeyLength];
            for(var i = 0; i < BleCcm.KeyLength; i++)
            {
                // enc_key_load stores the session key exactly as the AES block produced it,
                // so it is already in the order BleCcm wants. The reversal that used to be
                // here compensated for RunAesBlock feeding memory-order bytes to AES; with
                // the AES block's own endianness modelled, compensating again would undo it.
                crypt.Key[i] = sysbus.ReadByte(cs + (ulong)(CsSessionKeyOffset + i));
            }
            crypt.Iv = new byte[BleCcm.IvLength];
            for(var i = 0; i < BleCcm.IvLength; i++)
            {
                crypt.Iv[i] = sysbus.ReadByte(cs + (ulong)(CsIvOffset + i));
            }
            return true;
        }

        // Read a 48-bit little-endian CCM packet counter out of the control structure.
        private ulong ReadPacketCounter(ulong cs, int offset)
        {
            var counter = 0UL;
            for(var i = 0; i < CsPacketCounterLength; i++)
            {
                counter |= (ulong)sysbus.ReadByte(cs + (ulong)(offset + i)) << (8 * i);
            }
            return counter;
        }

        private void WritePacketCounter(ulong cs, int offset, ulong counter)
        {
            for(var i = 0; i < CsPacketCounterLength; i++)
            {
                sysbus.WriteByte(cs + (ulong)(offset + i), (byte)(counter >> (8 * i)));
            }
        }

        // Encrypt an outgoing data PDU in place of the hardware. The link layer has ALREADY
        // added the MIC's 4 octets to the descriptor length (r_lld_con_tx_prog_new_packet
        // 0x4001a8e2: `if(tx_enc) len += 4`), so `pdu` arrives sized for the ciphertext and
        // MIC with only `len-4` octets of real plaintext in it; we fill the rest. Empty PDUs
        // are never encrypted (spec, and the ROM's own len<5 boundary in r_lld_con_tx).
        private byte[] EncryptConnPdu(byte[] pdu)
        {
            if(!TryGetConnCrypt(out var crypt) || !crypt.TxEnabled || pdu.Length < 2 + BleCcm.MicLength + 1)
            {
                return pdu;
            }
            // BT Core Vol 6 Part E, 1 (packet counter) and Vol 6 Part B §5.1.3 (ARQ): the
            // CCM packet counter increments once per NEW link-layer PDU, not once per
            // transmission attempt. A PDU still eligible for retransmission -- its
            // descriptor not yet acked -- must go back on air with the SAME ciphertext,
            // MIC and counter as before, or the peer's receive counter (which only ever
            // advances on a PDU it actually authenticates) desyncs from ours on the very
            // first retry.
            //
            // pendingTxDesc is already the ARQ's "this descriptor is still unconfirmed"
            // signal (TryFetchConnTxPdu sets it on every fetch, ConfirmConnTx clears it
            // once the peer's NESN flip acks it) so a second fetch of the same descriptor
            // while it is still pending IS a retransmission -- reuse the ciphertext cached
            // under that descriptor instead of re-encrypting.
            //
            // Measured against a real Zephyr peripheral (peripheral_hids on an nRF52840):
            // our C3 retransmitted one logical LL_START_ENC_RSP 44 times, incrementing the
            // counter each time, and the peer disconnected with reason 0x3d
            // (BT_HCI_ERR_TERM_DUE_TO_MIC_FAIL) on the very first retry it had to decrypt.
            //
            // Only the sealed ciphertext is cached, not the whole PDU: StampSeq already
            // wrote this call's current SN/NESN into pdu[0], and NESN can legitimately
            // change between attempts (it acks the PEER's transmissions, independent of
            // whether OUR PDU is new or a retry). That is safe to rebuild fresh every time
            // because BleCcm masks NESN/SN/MD out of the AAD (HeaderAadMask) -- the
            // ciphertext itself does not depend on them.
            byte[] sealed_;
            if(pendingTxDesc != 0 && pendingTxDesc == txCipherDesc)
            {
                sealed_ = txCipherPayload;
            }
            else
            {
                var plaintext = pdu.Skip(2).Take(pdu.Length - 2 - BleCcm.MicLength).ToArray();
                var counter = ReadPacketCounter(crypt.ControlStructure, CsTxCounterOffset);
                var nonce = BleCcm.BuildNonce(counter, connRole == ConnRole.Master, crypt.Iv);
                sealed_ = BleCcm.Encrypt(crypt.Key, nonce, pdu[0], plaintext);
                WritePacketCounter(crypt.ControlStructure, CsTxCounterOffset, counter + 1);
                if(pendingTxDesc != 0)
                {
                    txCipherDesc = pendingTxDesc;
                    txCipherPayload = sealed_;
                }
                M5Trace($"ccm tx ctr={counter} plain={plaintext.Length} -> {sealed_.Length}B");
            }

            var result = new byte[2 + sealed_.Length];
            result[0] = pdu[0];
            result[1] = (byte)sealed_.Length;
            sealed_.CopyTo(result, 2);
            return result;
        }

        // Decrypt an incoming data PDU, returning the plaintext PDU. `micError` reports an
        // authentication failure, which the caller surfaces through the RX descriptor exactly
        // as the hardware does — r_lld_con_rx (0x4001a214) tests status bit 4 and tears the
        // connection down with a MIC failure when it is set.
        private byte[] DecryptConnPdu(byte[] pdu, out bool micError)
        {
            micError = false;
            if(!TryGetConnCrypt(out var crypt) || !crypt.RxEnabled || pdu.Length < 2 + BleCcm.MicLength + 1)
            {
                return pdu;
            }
            var ciphertext = pdu.Skip(2).ToArray();
            var counter = ReadPacketCounter(crypt.ControlStructure, CsRxCounterOffset);
            var nonce = BleCcm.BuildNonce(counter, connRole == ConnRole.Slave, crypt.Iv);
            micError = !BleCcm.TryDecrypt(crypt.Key, nonce, pdu[0], ciphertext, out var plaintext);
            if(micError)
            {
                // BT Core Vol 6 Part E, 1: the receive packet counter only advances for a
                // PDU that authenticates. A failed check means either a genuinely corrupt
                // PDU (rare on this deterministic medium) or -- the case this model has to
                // get right -- the peer retransmitting a PDU whose counter we already
                // advanced past. Advancing here on failure as well as on success is what
                // turns that single desync into a permanent one: every subsequent
                // retransmission then fails too, since the nonce never comes back into
                // agreement.
                this.WarningLog("Link-layer CCM: MIC check failed on a {0}-byte data PDU (counter {1})", pdu.Length, counter);
            }
            else
            {
                WritePacketCounter(crypt.ControlStructure, CsRxCounterOffset, counter + 1);
            }

            // Keep the ON-AIR length (payload + MIC) in the PDU: the link layer subtracts the
            // MIC's 4 octets itself once it sees RX encryption is on.
            var result = new byte[2 + ciphertext.Length];
            result[0] = pdu[0];
            result[1] = (byte)ciphertext.Length;
            plaintext.CopyTo(result, 2);
            M5Trace($"ccm rx ctr={counter} {ciphertext.Length}B micOk={!micError}");
            return result;
        }

        private struct ConnCrypt
        {
            public ulong ControlStructure;
            public byte[] Key;
            public byte[] Iv;
            public bool TxEnabled;
            public bool RxEnabled;
        }

        // Master side: transmit this connection event's packet shortly after the event
        // window opens (same arm delay as adv TX, so the sch_prog slot is armed and the
        // slave's window — anchored to the same CLKN by the shared LLData — is open).
        // The master opens every connection event by transmitting; per BT Core Vol 6 Part B
        // §4.5.1 the event's anchor point IS that transmission, so it goes out at the
        // programmed start with no delay of ours in between.
        private void TryConnEventTx()
        {
            if(connRole != ConnRole.Master)
            {
                return;
            }
            // connRole survives a disconnect (it is never cleared), so without this the
            // master keeps pushing connection data PDUs into whatever event is running --
            // including the SCAN events it starts again after the link drops.
            if(radioEventCtrlAddr == 0 || !IsConnectionEventSlot(radioEventCtrlAddr, out _))
            {
                return;
            }
            var pdu = BuildConnTxPdu();
            M5Trace($"conn event TX (master, {pdu.Length}B, hdr=0x{pdu[0]:X2})");
            SendConnPdu(pdu);
        }

        // On-air duration of a BLE 1 Mbps uncoded packet: 1 preamble + 4 access-address +
        // the PDU (header, length, payload) + 3 CRC bytes, at 8 us per byte. The medium
        // itself is instantaneous -- a frame is delivered at the instant its transmission
        // starts -- so a receiver's timestamp is the packet's start, which is what the RX
        // descriptor's CLKN means. But T_IFS is defined from the END of one packet to the
        // START of the next (Core Vol 6 Part B 4.1.1), and the link layer's own arithmetic
        // relies on it: r_lld_init_process_pkt_rx_adv_ind_or_direct_ind derives the end of
        // the CONNECT_IND as adv_rx + adv_air_time + T_IFS + connind_air_time, and picks
        // WinOffset against that. Turning a response around T_IFS after the *start* of what
        // we received therefore transmits it one packet duration early, and the peer's
        // anchor comes out that much off.
        private static ulong AirTimeMicroseconds(byte[] pdu, BlePhy rate)
        {
            return BleAirTime.Microseconds(pdu.Length, rate);
        }

        // T_IFS turnaround for an autonomous response to a frame we just received. The rate
        // comes from the same place the RX descriptor's rate code does, so the duration we
        // charge and the rate we report to the link layer cannot drift apart.
        // Measured from the received packet's start on air.
        private ulong TifsAfter(byte[] received)
        {
            var fullMicroseconds = AirTimeMicroseconds(received, ActivePhyRate) + TifsMicroseconds;
            if(!receiveTransmitStartHalfUs.HasValue)
            {
                return fullMicroseconds;
            }
            var dueHalfUs = receiveTransmitStartHalfUs.Value + fullMicroseconds * 2;
            var nowHalfUs = NowHalfMicroseconds();
            return dueHalfUs > nowHalfUs ? (dueHalfUs - nowHalfUs) / 2 : 0;
        }

        // The PHY rate the firmware programmed for the armed activity. r_lld_con_start
        // writes CS+4 as (tx_rate << 2) | rx_rate | 0x1100, and the RX descriptor's rate
        // code at +6 bits[15:14] is the same encoding -- r_lld_adv_pkt_rx_connect_post
        // indexes the per-rate timestamp correction table at 0x3fcdfc94 with it. Reading
        // the CS rather than assuming a rate is what keeps the two consistent.
        // The medium charges this radio's frames at the PHY the armed control structure
        // selects (IRadioWithTransmitPhy), the same field the air time below is read from.
        public BlePhy TransmitPhy => ActivePhyRate;

        private BlePhy ActivePhyRate
        {
            get
            {
                switch(CsPhyRate)
                {
                case PhyRate.Uncoded2Mbps:
                    return BlePhy.Uncoded2Mbps;
                case PhyRate.CodedS8:
                    return BlePhy.CodedS8;
                case PhyRate.CodedS2:
                    return BlePhy.CodedS2;
                default:
                    return BlePhy.Uncoded1Mbps;
                }
            }
        }

        private PhyRate CsPhyRate => TryResolveArmedControlStructure(out var csBase, out _)
            ? (PhyRate)(sysbus.ReadWord(csBase + CsRateOffset) & CsRateMask)
            : PhyRate.Uncoded1Mbps;

        // TX done is not raised here but with the RX done of the acknowledging packet.
        // r_rwble_isr (0x4002e64a) dispatches bits 5/2/6/1 through the four adjacent slots
        // _DAT_ram_3fcdff8c + 0x6c0/0x6cc/0x6d0/0x6d4 -- a per-activity {END, RX, SKIP, TX}
        // ISR vtable rebound to whichever activity owns the radio -- so bit 1 reaches
        // r_lld_con_tx_isr (0x4001b47e) only while the connection event is the running
        // activity.
        private void SendConnPdu(byte[] pdu)
        {
            // Remembered for the MD test in ShouldContinueConnEvent: this is the header
            // that actually went on air, so our half of "either side has more data" is
            // read back from the transmission rather than recomputed.
            lastConnTxHeader = pdu[0];
            SendOnMedium(pdu);
            if(!radioEventLive || radioEventCtrlAddr == 0)
            {
                return;
            }
            HoldConnEventForReply(pdu);
            // r_sch_prog_tx_isr (0x400308dc) refuses to run unless the running slot's
            // STATE field says a frame happened: `(slot_ctrl >> 3) & 6` must be non-zero,
            // else it asserts sch_prog.c line 0xe8 -- the 232 the firmware prints. STATE 2
            // is "frame in progress", which is what a transmission puts the slot into,
            // exactly as the RX delivery path does. (Not 3: that is the serviced state the
            // event end writes, and setting it early ends the slot before END is raised.)
            var ctrl = sysbus.ReadWord(radioEventCtrlAddr);
            sysbus.WriteWord(radioEventCtrlAddr, (ushort)((ctrl & ~SchProgTypeMask) | (2 << 3)));
        }

        // Whether this connection event carries on past the pair that just completed.
        // Core Vol 6 Part B 4.5.6: the event stays open while either device's last PDU had
        // MD set, and closes only when both are clear. Both inputs are supplied, never
        // guessed -- the peer's MD arrives on air in the header we just received, and ours
        // rode out in the TX descriptor's TXPHCE byte, which the link layer wrote and
        // StampSeq preserves. The master is the only side that needs this: the slave
        // already answers every PDU it hears in an armed event, so once the master keeps
        // transmitting the exchange continues by itself.
        //
        // This is what a single pair per event was costing: a peripheral with an ATT
        // response and a notification queued sets MD on the response, and silicon sends
        // both in the one event, response first. Closing the event after the first pair
        // pushed the notification into the next event and inverted the two.
        private bool ShouldContinueConnEvent(byte receivedHeader)
        {
            return ((receivedHeader | lastConnTxHeader) & MoreDataBit) != 0;
        }

        // The scheduler's programmed duration is the event's MINIMUM: r_lld_con_evt_time_update
        // (ROM 0x40019324) writes the same slot count into CS+0x1E (MINEVTTIME) and CS+0x20
        // (MAXEVTIME) -- 0x4C = 47.5 ms for a 50 ms interval -- and the sch_prog slot only
        // covers the first frame pair. Real RW hardware keeps the event running past that
        // while either side's last PDU had MD set, and stops at MAXEVTIME (Core Vol 6 Part B
        // 4.5.6). So after a transmission that keeps the exchange open, hold the event
        // until the reply can have finished: T_IFS plus a maximal data PDU, bounded by
        // MAXEVTIME.
        private void HoldConnEventForReply(byte[] pdu)
        {
            if(((pdu[0] | lastConnRxHeader) & MoreDataBit) == 0)
            {
                return;
            }
            if(!TryResolveConnControlStructure(out var cs))
            {
                return;
            }
            var maxEvtSlots = sysbus.ReadWord(cs + CsMaxEvtTimeOffset);
            if(maxEvtSlots == 0)
            {
                return;
            }
            var replyDone = NowHalfMicroseconds()
                + (AirTimeMicroseconds(pdu, ActivePhyRate) + TifsMicroseconds
                    + AirTimeMicroseconds(new byte[MaxDataChannelPduLength], ActivePhyRate)) * 2;
            var maxEnd = radioEventStartHalfUs + maxEvtSlots * SlotMicroseconds * 2;
            var holdUntil = Math.Min(replyDone, maxEnd);
            if(holdUntil > txInFlightUntilHalfUs)
            {
                txInFlightUntilHalfUs = holdUntil;
            }
        }

        // Transmit the next PDU of an event already in progress. The descriptor is fetched
        // inside the callback rather than now, because the hardware reads it at the moment
        // it transmits: building it early would claim a descriptor (and set pendingTxDesc)
        // for a packet the event may end before sending, and the next ack would then
        // confirm a PDU that never went on air.
        private void ContinueConnEvent(ulong delayMicroseconds, ulong epoch)
        {
            var ts = machine.LocalTimeSource;
            var when = LocalDelayMicroseconds(delayMicroseconds);
            ts.ExecuteInSyncedState(_ =>
            {
                // The radio is off once the programmed duration expires, so a continuation
                // that misses its window transmits nothing. This is also what bounds the
                // exchange: the scheduler's event duration ends it, exactly as on hardware,
                // so no iteration count is needed here.
                if(radioEventLive && epoch == radioEventEpoch)
                {
                    SendConnPdu(BuildConnTxPdu());
                }
            }, when);
        }

        private void ScheduleConnFrameSend(byte[] pdu, ulong delayMicroseconds)
        {
            var ts = machine.LocalTimeSource;
            var when = LocalDelayMicroseconds(delayMicroseconds);
            ts.ExecuteInSyncedState(_ => SendConnPdu(pdu), when);
        }

        private void ScheduleFrameSend(byte[] pdu, ulong delayMicroseconds)
        {
            var ts = machine.LocalTimeSource;
            var when = LocalDelayMicroseconds(delayMicroseconds);
            ts.ExecuteInSyncedState(_ => SendOnMedium(pdu), when);
        }

        // --- Data-channel selection (BT Core Vol 6 Part B §4.5.8) ---------------
        //
        // The RW-BLE core hops in hardware from fields the link layer writes into the
        // connection control structure, so the channel is read from there at every event
        // and the model keeps no hop state of its own (decompiled C3 ROM, lld_con.c):
        //
        //   CS+0x16 HOPCNTL  bit15 FH_EN, bit14 CSA#2 (the CONNECT_IND ChSel bit),
        //                    bits12:8 hopIncrement, bits5:0 CH_IDX
        //                    (r_lld_con_start writes 0x8000 | ChSel<<14 | hop<<8)
        //   CS+0x22..0x26    channel map, data channels 0..36 as bits 0..36
        //                    (r_lld_con_start; a CHANNEL_MAP_IND is applied here at its
        //                    instant by the LL, so the model follows it for free)
        //   CS+0x50          connEventCounter, written by r_lld_con_evt_start_cbk as the
        //                    previous counter plus the events elapsed -- skipped events
        //                    (latency, scheduling conflicts) included
        //   CS+0x0C/0x0E     access address, whose halves XOR to the CSA#2 identifier
        //
        // For CSA#1 the same callback writes this event's unmapped channel into CH_IDX
        // ((events elapsed * hop + last) mod 37), so the hardware only remaps it. For
        // CSA#2 it computes the channel from the counter. With FH_EN clear CH_IDX is the
        // channel as programmed.
        private int DataChannelFromControlStructure(ulong cs)
        {
            var hopControl = sysbus.ReadWord(cs + CsHopControlOffset);
            var channelIndex = hopControl & HopChannelIndexMask;
            if((hopControl & HopFrequencyHopEnableBit) == 0)
            {
                return channelIndex;
            }
            var used = new List<int>();
            for(var channel = 0; channel < DataChannelCount; channel++)
            {
                var word = sysbus.ReadWord(cs + CsChannelMapOffset + (ulong)(channel / 16) * 2);
                if((word & (1 << (channel % 16))) != 0)
                {
                    used.Add(channel);
                }
            }
            if(used.Count == 0)
            {
                return channelIndex; // an empty map is invalid on air; keep what was programmed
            }
            int candidate;
            if((hopControl & HopCsa2Bit) != 0)
            {
                var accessAddress = sysbus.ReadDoubleWord(cs + CsAccessAddressOffset);
                var channelId = (ushort)((accessAddress >> 16) ^ (accessAddress & 0xFFFF));
                var counter = sysbus.ReadWord(cs + CsEventCounterOffset);
                var prnE = ChannelPrnE(counter, channelId);
                candidate = prnE % DataChannelCount;
                return used.Contains(candidate) ? candidate : used[(int)(((uint)used.Count * prnE) >> 16)];
            }
            candidate = channelIndex % DataChannelCount;
            return used.Contains(candidate) ? candidate : used[candidate % used.Count];
        }

        private static ushort ChannelPrnE(ushort counter, ushort channelId)
        {
            var prn = (ushort)(counter ^ channelId);
            for(var i = 0; i < 3; i++)
            {
                prn = (ushort)((ReverseBits((byte)(prn >> 8)) << 8) | ReverseBits((byte)prn));
                prn = (ushort)(prn * 17 + channelId);
            }
            return (ushort)(prn ^ channelId);
        }

        private static byte ReverseBits(byte value)
        {
            var result = 0;
            for(var i = 0; i < 8; i++)
            {
                result = (result << 1) | ((value >> i) & 1);
            }
            return (byte)result;
        }

        private static uint ReadConnectIndAccessAddress(byte[] connectIndPdu)
        {
            if(connectIndPdu.Length < ConnectIndLlDataOffset + 4)
            {
                return AdvAccessAddress;
            }
            return (uint)(connectIndPdu[ConnectIndLlDataOffset]
                | (connectIndPdu[ConnectIndLlDataOffset + 1] << 8)
                | (connectIndPdu[ConnectIndLlDataOffset + 2] << 16)
                | (connectIndPdu[ConnectIndLlDataOffset + 3] << 24));
        }

        // The single medium-TX chokepoint: prefix the channel PDU with its on-air access
        // address, which is what a BLEMedium frame is defined to carry. Advertising-channel
        // PDUs (ADV_IND, SCAN_REQ/RSP, CONNECT_IND) use the fixed 0x8E89BED6; once a
        // connection exists both peers use the AA the CONNECT_IND's LLData carried.
        private void SendOnMedium(byte[] pdu)
        {
            // The frame occupies the air from now until its air time elapses, and the
            // running event cannot END before it completes (see EndRadioEvent).
            var txEnd = NowHalfMicroseconds() + AirTimeMicroseconds(pdu, ActivePhyRate) * 2;
            if(txEnd > txInFlightUntilHalfUs)
            {
                txInFlightUntilHalfUs = txEnd;
            }
            // Take the AA from the armed control structure, which is where the firmware
            // put it -- the silicon stamps that field and nothing else. Deriving it from
            // connRole instead made the prefix a function of our own state: connRole is
            // set to Master on the first connection and never returns to None, so every
            // later CONNECT_IND went out prefixed with the connection AA it was itself
            // announcing, on a channel where the peer only listens for 0x8E89BED6. The
            // first connection of a run worked and every reconnect was ignored.
            var accessAddress = TryResolveArmedControlStructure(out var csBase, out _)
                ? sysbus.ReadDoubleWord(csBase + CsAccessAddressOffset)
                : (connRole == ConnRole.None ? AdvAccessAddress : connAccessAddress);
            M5Trace($"tx type={pdu[0] & 0xF} len={pdu.Length} aa=0x{accessAddress:X8} ch={currentChannel}");
            var frame = new byte[AccessAddressLength + pdu.Length];
            frame[0] = (byte)accessAddress;
            frame[1] = (byte)(accessAddress >> 8);
            frame[2] = (byte)(accessAddress >> 16);
            frame[3] = (byte)(accessAddress >> 24);
            pdu.CopyTo(frame, AccessAddressLength);
            FrameSent?.Invoke(this, frame);
        }

        // The control structure of the event currently armed in the scheduler, taken from
        // that slot's CS pointer. Returns false when no event is armed. actId is the CS's
        // index within the region, which is also the tag the LL expects in RX descriptors:
        // r_lld_rxdesc_check (0x400203aa) returns 0 unless `desc[+12] >> 11 == act_id`, so
        // a wrong tag makes the LL discard a descriptor the model already filled — the
        // controller looks perfectly healthy (in-window RX, interrupt raised, ISR runs) and
        // the host simply never sees a device.
        //
        // Deriving it from the slot replaces two earlier guesses: a hardcoded 0, and then a
        // read of the ROM's own `lld_scan_env`/`lld_init_env` software globals. Silicon has
        // no access to those globals; it has the CS pointer the LL wrote into the slot.
        private bool TryResolveArmedControlStructure(out ulong csBase, out int actId)
        {
            csBase = 0;
            actId = 0;
            if(!IsEventSlotArmed())
            {
                return false;
            }
            var csOffset = (uint)sysbus.ReadWord(radioEventCtrlAddr + SchProgCsPtrOffset) * 2;
            if(csOffset < ControlStructureRegionOffset)
            {
                return false;
            }
            csBase = ResolveEmOffset(csOffset);
            actId = (int)((csOffset - ControlStructureRegionOffset) / ControlStructureStride) & 0x1F;
            M5Trace($"cs resolve: csOffset=0x{csOffset:X} base=0x{csBase:X} actId={actId}");
            return csBase != 0;
        }

        // Resolve an EM segment's physical DRAM address from its mapping register.
        // The LL programs 0x60031204 + index*4 with (ptr>>2)&0x3FFFF; the physical EM
        // address is reconstructed as 0x3fc00000 | ((reg<<2) & 0xFFFFC). Verified live.
        private ulong ResolveEmSegment(int index)
        {
            var mapOffset = EmMapBase + index * 4;
            if(!windowStorage.TryGetValue(mapOffset, out var reg))
            {
                return 0;
            }
            return EmPhysBase | (((ulong)reg << 2) & EmPtrMask);
        }

        // --- M3 groundwork: Exchange-Memory RX descriptor contract -------------
        // Faithful replica of the ROM r_emi_get_mem_addr_by_offset (0x40006976): resolve a
        // BLE Exchange-Memory byte offset to its physical DRAM address via the em_base_reg_lut
        // (ROM 0x3ff1f518) + the mapping registers at 0x60031204. Used by FillRxDescriptor.
        private ulong ResolveEmOffset(uint offset)
        {
            var region = offset >> 10;                                   // /1024
            var lutEntry = emBaseRegLut + region * 4;
            var mapIdx = sysbus.ReadByte(lutEntry);                      // mapping-register index
            var regionBase = sysbus.ReadWord(lutEntry + 2);             // per-region base offset
            var mapReg = sysbus.ReadDoubleWord(0x60031204 + (ulong)mapIdx * 4);
            var phys = EmPhysBase | (((ulong)mapReg << 2) & EmPtrMask);
            return phys + (offset - regionBase);
        }

        // M3 groundwork (proven, not yet wired): emulate the RW-BLE HW filling the current RX
        // descriptor + buffer with a received ADV PDU so r_lld_rxdesc_check_hack /
        // r_lld_scan_process_pkt_rx_hack accept it and (once the scan-event window engine exists)
        // emit an HCI LE Advertising Report. Descriptor ring = EM offset 0x1000, 20-byte linked
        // nodes, index = *(p_lld_env+216). Fields decoded from ROM r_lld_rxdesc_check (0x4002022c)
        // + the patched processor (0x40384c26 / adv-rep 0x40384eb4):
        //   +0  halfword: bit15 = rxdone (HW sets), bits0..14 = next-desc EM offset
        //   +2  halfword: rx status; bit15 = "empty/owned" (HW clears on fill); error bits
        //                 masked 0x602d must be 0 for a good packet
        //   +4  halfword: OTA PDU header (byte0 = header, byte1 = length)
        //   +18 halfword: EM offset of the payload buffer (AdvA + AdvData)
        // This is called only from the deferred scan-RX delivery path; see
        // docs/esp32c3-ble-m3-continuous-scan.md.
        private void FillRxDescriptor(byte[] frame, int activityTag = 0, bool micError = false, bool crcError = false)
        {
            if(frame.Length < 2)
            {
                return;
            }
            var pLldEnv = sysbus.ReadDoubleWord(lldEnvPointer);
            if(pLldEnv == 0)
            {
                return;
            }
            var rxIdx = sysbus.ReadByte(pLldEnv + 216);
            var desc = ResolveEmOffset(0x1000) + (ulong)rxIdx * 20;

            // Payload buffer (frame minus the 2-byte OTA header — AdvA at offset 0) at the
            // +18 handle. Proven end-to-end: writing the header into the buffer shifts the
            // HCI report's AdvA/AdvData by 2 (the header lands in the report's addr field);
            // the ROM report builder reads AdvA at payload+0 (r_lld_scan_process_pkt_rx_adv_rep
            // 0x400248f0: source = em_addr(payload_handle + pdu_info[2]) with pdu_info[2]=0).
            var handle = sysbus.ReadWord(desc + 18);
            var bufPhys = ResolveEmOffset(handle);
            for(var i = 2; i < frame.Length; i++)
            {
                sysbus.WriteByte(bufPhys + (ulong)(i - 2), frame[i]);
            }

            // Header (byte0) + length (byte1) copied into the descriptor at +4.
            sysbus.WriteWord(desc + 4, (ushort)(frame[0] | (frame[1] << 8)));
            // +6 low byte = raw RSSI. Silicon oracle (2 real C3 boards, 2026-07-23):
            // the report's RSSI byte equals this raw byte unchanged (rwip_rf.rssi_convert
            // is identity on this path), and desk-distance boards report -36..-40 dBm.
            // Inject 0xD8 (-40, two's complement) so sim reports carry a realistic value.
            // Bits[15:14] are the PHY rate the packet came in on: r_lld_adv_pkt_rx_connect_post
            // (0x40015d4a) does `desc[+6] >> 14` and uses it to index the per-rate timestamp
            // correction table at 0x3fcdfc94, and copies it on into the connect message.
            sysbus.WriteWord(desc + 6, (ushort)(((uint)CsPhyRate << 14) | 0x00D8));
            // +8/+10 = RX timestamp: CLKN slot at reception, low 16 bits at +8, high 12
            // bits at +10 (r_lld_init_process_pkt_rx_adv_ind_or_direct_ind 0x4001d8e6 reads
            // both, asserts line 997 unless (+10 << 16) has no bits above 0xFFF, and derives
            // the CONNECT_IND anchor from them; stale zeros here scheduled the first
            // connection event 80 slots in the past — M5 fault-loop). The +12 low 10 bits
            // are the sub-slot fine time (0 = slot boundary), shared with the tag field.
            // Timestamp the packet's start on air. Outside a medium delivery (the deferred
            // scan-RX path re-fills a descriptor later) there is no transmit instant to use,
            // so fall back to the local clock.
            //
            // NOTE (2026-08-04, measured): moving this to end-of-packet (start + airtime),
            // on the theory that hardware latches its receive reference at the end of the
            // frame, is WRONG here -- it moved the slave's lastsync one half-slot later and
            // left the initiator's anchor untouched, widening the two ends' disagreement and
            // taking the cycle bench from 4 connections to 0. The initiator's anchor does not
            // flow through this field, and the ROM's per-rate correction table (0x3fcdfc94)
            // appears to already assume this reference. Do not re-apply without a silicon
            // measurement of what instant the hardware actually latches.
            var rxHalfUs = receiveTransmitStartHalfUs ?? NowHalfMicroseconds();
            var rxClkn = (uint)(rxHalfUs / HalfSlotHalfMicroseconds) & ClknMask;
            // What the model reports as the reception instant, beside what the firmware
            // then derives from it (ietl ref54) -- the pair that says whether the master's
            // anchor error is introduced here or downstream of here.
            M5Trace($"rxts desc=0x{desc:X} clkn={rxClkn} halfus={rxHalfUs} nowclkn="
                + $"{(uint)(NowHalfMicroseconds() / HalfSlotHalfMicroseconds) & ClknMask}"
                + $" len={frame.Length} hdr=0x{frame[0]:X2} medium={(receiveTransmitStartHalfUs.HasValue ? 1 : 0)}");
            sysbus.WriteWord(desc + 8, (ushort)(rxClkn & 0xFFFF));
            sysbus.WriteWord(desc + 10, (ushort)((rxClkn >> 16) & 0xFFF));
            // +12 bits[15:11] = activity/link-id tag: ROM r_lld_rxdesc_check (0x400203aa)
            // rejects the descriptor unless this matches the caller's activity index. A
            // scan-only node's scan activity is index 0, so the tag is 0 — but the field
            // must be written (stale EM content here made the check fail silently).
            // M5: connection deliveries carry the connection activity's tag instead.
            // Bits[9:0] are the sub-half-slot fine RX time, stored in the SAME complement
            // the FINETIMECNT register uses: r_lld_adv_pkt_rx_connect_post decodes it as
            // `0x270 - (desc[+12] & 0x3ff)`, i.e. elapsed = 624 - value. Leaving it 0
            // therefore claimed the maximum 624 half-us (~312 us) of offset on every
            // received packet, and that offset feeds the connection anchor directly.
            var fineComplement = (HalfSlotHalfMicroseconds - 1)
                - (rxHalfUs % HalfSlotHalfMicroseconds);
            sysbus.WriteWord(desc + 12,
                (ushort)(((activityTag & 0x1F) << 11) | (uint)(fineComplement & 0x3FF)));
            // +14 = peer resolving-list entry pointer. r_lld_adv_pkt_rx_connect_ind
            // (0x40016012) treats any nonzero value as a RAL entry and indexes
            // (value - 0xc60) / 0x34 with it, so stale EM content here sends the
            // CONNECT_IND handler down the privacy branch on garbage. No RAL entry is in
            // play on this path: write the zero that means "resolve from the header".
            sysbus.WriteWord(desc + 14, 0);
            M5Trace($"rxdesc idx={rxIdx} tag={activityTag} len={frame[1]}");
            // +16 low 6 bits must be < the length byte (r_lld_scan_process_pkt_rx_hack
            // 0x40384daa sanity compare); zero always satisfies it.
            sysbus.WriteWord(desc + 16, 0);
            // Clear the status halfword: bit15 (empty) -> 0, no error bits — except a failed
            // MIC, which is reported here rather than by dropping the packet, because the LL
            // has to see it to terminate the connection with the right reason code.
            sysbus.WriteWord(desc + 2, (ushort)((micError ? RxMicErrorBit : 0) | (crcError ? RxCrcErrorBit : 0)));
            // Set rxdone (bit15) in +0, preserving the next-desc pointer in bits0..14.
            var d0 = sysbus.ReadWord(desc);
            sysbus.WriteWord(desc, (ushort)(d0 | 0x8000));
        }

        // Sim time on the BLE clock's own scale. Virtual-time ticks are nanoseconds, so
        // a half-microsecond is exactly 500 of them and this stays lossless.
        // IHasClockScale: how fast the controller's slot clock runs relative to
        // virtual time. Everything the link layer times -- anchor points, window
        // widening, CLKN -- is in this local timebase; only the conversions below touch
        // virtual time, so a node with a fast crystal drifts against its peer the way
        // the receive window widening (CS+0x1A) exists to cover.
        public double ClockScale
        {
            get => clockScale;
            set
            {
                if(value <= 0)
                {
                    throw new RecoverableException("ClockScale must be positive.");
                }
                clockScale = value;
            }
        }

        private ulong NowHalfMicroseconds()
        {
            return ToLocalHalfMicroseconds(machine.LocalTimeSource.ElapsedVirtualTime);
        }

        // A virtual-time instant on this controller's clock.
        private ulong ToLocalHalfMicroseconds(TimeInterval virtualTime)
        {
            return (ulong)(virtualTime.Ticks * clockScale) / HalfMicrosecondTicks + timeBaseMicroseconds * 2;
        }

        // The virtual-time instant `localDelayHalfUs` of this controller's clock from now.
        private TimeStamp LocalDelay(ulong localDelayHalfUs)
        {
            var ts = machine.LocalTimeSource;
            return new TimeStamp(ts.ElapsedVirtualTime + FromHalfMicroseconds(localDelayHalfUs), ts.Domain);
        }

        private TimeStamp LocalDelayMicroseconds(ulong localDelayUs)
        {
            return LocalDelay(localDelayUs * 2);
        }

        private TimeInterval FromHalfMicroseconds(ulong halfMicroseconds)
        {
            return TimeInterval.FromNanoseconds((ulong)(halfMicroseconds * HalfMicrosecondTicks / clockScale));
        }

        // Interrupt-matrix line indices (== Connections keys), wired in the .repl to the
        // ETS_*_SOURCE numbers. RWBLE is the main link-layer interrupt.
        private const int RwbleLine = 0;   // ETS_RWBLE_INTR_SOURCE = 8
        private const int InterruptLineCount = 4; // RWBLE, RWBT, BT_MAC, BT_BB

        // RW-BLE's native time unit is the HALF-slot = 312.5 us, and CLKN is a 28-bit
        // free-running half-slot counter. 312.5 does not fit an integer number of
        // microseconds, which is how this was previously stored as "625 us" — the
        // right number, the wrong unit, and every derived time came out 2x too long.
        // Everything on the clock path is therefore kept in HALF-MICROSECONDS, where
        // the half-slot is exactly 625 of them and no rounding is needed.
        //
        // Confirmed against the ROM: r_rwip_timer_10ms_set converts its 10 ms argument
        // to base ticks with `param << 5` (x32), and 10 ms / 32 = 312.5 us. The
        // firmware also derives the connection interval as CONNECT_IND-Interval x 4
        // (1.25 ms / 312.5 us), which x2 into 625 us slots could not produce.
        //
        // NOT to be confused with the 0.625 ms unit the Bluetooth spec uses for HCI
        // advertising/scan intervals: that one really is 625 us. Both appear in this
        // file and they are different quantities.
        private const ulong HalfSlotHalfMicroseconds = 625;
        // transmitWindowDelay for an uncoded PHY, BT Core Vol 6 Part B 4.5.3: the transmit
        // window opens this long after the end of the CONNECT_IND, before WinOffset.
        private const ulong TransmitWindowDelayHalfUs = 4 * HalfSlotHalfMicroseconds;
        // The 1.25 ms unit both WinOffset and Interval are expressed in (Vol 6 Part B
        // 2.4.2.1). Numerically equal to TransmitWindowDelayHalfUs at an uncoded PHY,
        // but a different quantity -- the delay scales with the PHY, this never does.
        private const ulong ConnUnitHalfMicroseconds = 2500;
        private const uint ClknMask = 0x0FFFFFFF;
        // Virtual-time ticks per half-microsecond (TimeInterval ticks are nanoseconds).
        private const ulong HalfMicrosecondTicks = 500;
        // Half-slots per 10 ms, straight from r_rwip_timer_10ms_set's `param << 5`.
        private const uint TicksPer10Ms = 32;

        // Event-anchor timer INTSTAT/INTCNTL bits (from r_rwip_isr @0x4002f4ec):
        // bit 11 = fine timer (near events / scan), bit 10 = coarse timer (far events).
        private const uint FineTimerBit = 0x800;
        private const uint CoarseTimerBit = 0x400;
        // Clock/event target (bit 9): the connection-event anchor. r_rwip_isr 0x4002f576
        // ACKs 0x200 and dispatches its own handler; target register = 0x024.
        private const uint ClockTargetBit = 0x200;
        // Software interrupt: requested via RWBLECNTL bit 27, delivered as INTSTAT bit 12
        // and dispatched to r_rwip_sw_int_handler. See Registers.Control.
        private const uint SwIntBit = 0x1000;
        private const uint CscntBit = 0x1;      // BLEINTSTAT CSCNT slot tick -> r_rwip_wakeup_end (ROM r_rwip_isr dispatch 0x2e4)
        private const uint SleepBit = 0x8;      // BLEINTSTAT SLP -> r_rwip_wakeup (ROM r_rwip_isr dispatch 0x2e0)
        private const uint SwIntRequestBit = 0x08000000;
        // sch_prog dispatch bits (r_rwble_isr_hack table, M3 doc §1): bit2 = RX done,
        // bit5 = EOF/END. Used by the continuous-scan engine (OpenScanWindow/CloseScanWindow).
        private const uint RxDoneBit = 0x4;
        private const uint EndBit = 0x20;
        // Bit 1 = TX done, the RX-done bit's twin: r_rwble_isr (0x4002e64a) tests them
        // adjacently and dispatches bit1 through the RAM handler table at
        // _DAT_ram_3fcdff8c+0x6d4 and bit2 at +0x6cc. Bit 1 is enabled in every INTCNTL
        // mask the firmware programs in a live run (0x640166 / 0x640366 / 0x640966 /
        // 0x640b66). It reaches r_lld_con_tx_isr (0x4001b47e) -> r_lld_con_tx
        // (0x4001a394), the descriptor-reclaim loop.
        private const uint TxDoneBit = 0x2;
        // Single-block AES completion (bit 7): r_rwip_aes_encrypt enables it in INTCNTL
        // (|= 0x80) and pre-ACKs it in INTACK (= 0x80); r_rwip_crypt_isr_handler clears the
        // enable again on entry.
        private const uint CryptBit = 0x80;
        private const int AesKeyWords = 4;
        private const int AesBlockLength = 16;

        // --- M3: sch_prog scan-event tracking (continuous-scan engine, §4.1) ---
        // sch_prog_env base + curSlot offset. GDB/disassembly ground truth: the blob's
        // EM seg-0 (sch_prog) mapping-register index; index 1 is the adv CS (EmSegControlStructure).
        private const int EmSegSchProg = 0;
        // Each sch_prog slot's EM control word is 16 bytes apart (doc §5: "EM seg-0 [slot*16]").
        private const ulong SchProgSlotStride = 16;
        // Bit31 of the 0x100 push register: "this slot is now the hardware's".
        private const uint EventProgramGoBit = 0x80000000;
        // The sub-slot target is stored as (624 - us into the slot), the same complement
        // FINETIMECNT reads back; the ROM asserts it never exceeds 624.
        private const ushort SchProgFineMax = 624;
        // Control-word STATE field = bits [5:3] (see IsRxGateOpen for the full decoded
        // layout). r_sch_prog_end_isr_handler dispatches the slot callback for STATE in
        // {3,4,5}, passing a2 = (STATE==4); 4 is the EOF variant we signal at window close.
        private const ushort SchProgTypeMask = 0x38;
        private const ushort SchProgTypeDone = 4;
        // Slot +10 = the event's duration, in half-slots+fine on the same scale as its
        // start time. This is what decides how long the radio stays on, so the model has
        // no window length of its own.
        private const ulong SchProgDurationOffset = 10;
        // Post-service sentinel written back at event end: 0x0018 = all fields cleared with
        // STATE=3, which dispatches the slot callback with a2=0 (normal EOF). Leaving TYPE
        // bits set, or using STATE=4 (the a2=1 variant), was seen to jam the queue — the
        // firmware never reaped the slot or pushed again.
        private const ushort SchProgSlotServiced = 0x0018;
        // Non-zero priority injected into the 0x2D8 priority-dispatch vector so the ISR
        // services the interrupt (only its non-zeroness matters to the dispatch gate).
        private const uint IntPriorityLevel = 0xF;

        // The three BLE advertising channels reported to BLEMedium per event.
        // Descriptor PDU types transmitted at an adv event start (BT Core Vol 6 Part B
        // §2.3: ADV_IND, ADV_DIRECT_IND, ADV_NONCONN_IND, ADV_SCAN_IND).
        private static readonly int[] AdvTxPduTypes = { 0, 1, 2, 6 };
        // Advertising-channel PDU types (BT Core Vol 6 Part B §2.3) + T_IFS (§4.1.1).
        private const int AdvIndPduType = 0;
        // Advertising PDU header bit 6 = TxAdd (0 public, 1 random address).
        private const int AdvTxAddBit = 0x40;
        // Data-PDU header bit 4 (Core Vol 6 Part B 2.4.2): More Data.
        private const byte MoreDataBit = 0x10;
        private const int ScanReqPduType = 3;
        private const int ScanRspPduType = 4;
        private const int ConnectIndPduType = 5;
        // Header (2) + InitA (6) + AdvA (6) + LLData (22).
        private const int ConnectIndPduLength = 36;
        private const int DataChannelCount = 37;
        // Advertising PDU header bit 5 = ChSel (CSA#2 supported/selected).
        private const int ChSelBit = 0x20;
        // Empty data-channel PDU (LLID=1, len 0): what real RW HW transmits autonomously
        // in a connection event with no pending data.
        private static readonly byte[] EmptyDataPdu = { 0x01, 0x00 };
        private enum ConnRole { None, Master, Slave }
        private const int AdvScanIndPduType = 6;
        // RW-BLE PHY rate encoding, shared by the control structure and the RX descriptor.
        // Rates 2 and 3 are the coded ones: the ROM tests `(rate - 2) < 2` for coded on
        // every path that cares, and r_lld_con_start budgets 0xa90 for them against 0x148
        // for the uncoded rates.
        private enum PhyRate
        {
            Uncoded1Mbps = 0,
            Uncoded2Mbps = 1,
            CodedS8 = 2,
            CodedS2 = 3,
        }

        private const ulong TifsMicroseconds = 150;
        // Longest legacy advertising-channel PDU: 2-octet header + the 37-octet payload
        // maximum of Core Vol 6 Part B §2.3.
        private const int MaxAdvChannelPduLength = 2 + 37;
        private const int MaxDataChannelPduLength = 2 + 255;   // header + max LL payload incl. MIC
        private const ulong SlotMicroseconds = 625;
        private const int CsRateOffset = 4;
        private const uint CsRateMask = 0x3;

        // EM segment mapping table: register index i at window offset 0x204 + i*4.
        // phys = 0x3fc00000 | ((reg<<2) & 0xFFFFC). Index 1 is the adv control structure
        // (verified live: AA 0x8E89BED6 + CRC 0x555555 at CS+12/+16).
        private const long EmMapBase = 0x204;
        private const ulong EmPhysBase = 0x3fc00000;
        private const ulong EmPtrMask = 0xFFFFC;
        private const int EmSegControlStructure = 1;
        // ROM em_base_reg_lut, used by ResolveEmOffset (r_emi_get_mem_addr_by_offset replica).
        private readonly ulong emBaseRegLut;
        // ROM p_lld_env, r_modules_funcs_p, lld_con_env, lld_init_env, co_rate_to_phy -- see
        // the constructor comment for the per-SoC ROM addresses.
        private readonly ulong lldEnvPointer;
        private readonly ulong modulesFuncsP;
        private readonly ulong lldConEnv;
        private readonly ulong lldInitEnv;
        private readonly ulong coRateToPhy;
        // Every scheduler slot names the control structure its event belongs to: slot+8 is
        // the CS pointer as an EM *halfword* offset. Verified live on stock ESP-IDF, both
        // activities of one node: the scan event's slot reads 0x0200 (-> EM 0x400, act 0)
        // and the initiator's reads 0x022d (-> EM 0x45A, act 1). This is how the real RW
        // core knows which activity a radio event serves, so the model routes on it too
        // rather than on ROM software globals or on the slot's priority field.
        private const ulong SchProgCsPtrOffset = 8;
        // Control structures are packed one per activity from EM offset 0x400, stride 0x5A
        // (r_lld_init_start 0x4001ec98: `iVar27 = act_id * 0x5a` applied to
        // emi_get_mem_addr_by_offset(0x400) — the region segment 1 maps).
        private const uint ControlStructureRegionOffset = 0x400;
        private const uint ControlStructureStride = 0x5A;
        // Control-structure field offsets (r_lld_adv_start decode + live verification).
        private const int CsBdAddr0Offset = 6;          // own BD_ADDR bytes 0..5 at CS+6/+8/+10
        private const int CsInitPeerAddr0Offset = 0x2C;  // initiating CS: target peer BD_ADDR, 6 bytes
        private const int CsAccessAddressOffset = 12;   // adv-channel Access Address (0x8E89BED6)
        private const int CsAdvChannelMapOffset = 0x26; // advertising CS: bits 7:5 = channels 37..39
        private const int CsAdvChannelMapShift = 5;
        private const long AdvPacketIntervalRegisterOffset = 0x120; // bits 15:0, µs between ADV starts
        private const int CsHopControlOffset = 0x16;    // HOPCNTL, see DataChannelFromControlStructure
        private const int CsChannelMapOffset = 0x22;    // data channel map, 37 bits over 0x22..0x26
        private const int CsEventCounterOffset = 0x50;  // connEventCounter, written by the LL per event
        private const ushort HopFrequencyHopEnableBit = 0x8000;
        private const ushort HopCsa2Bit = 0x4000;
        private const int HopChannelIndexMask = 0x3F;
        // Initiator CS: the connection window the LL picked for the link it is about to
        // open. CS+0x20 holds WinSize*4 and CS+0x22 the interval, both matching the packed
        // LLData, which is what identifies +0x1E as the field read at TX time.
        //
        // NOT +0x44, despite CS+0x44 being the silicon-verified WinOffset of an established
        // connection (5/5 against the sniffer, hil-setups/c3-ble/winoff_probe.h). The two
        // are different moments in the same sequence and only +0x1E is populated at the one
        // this call site runs at:
        //   - here, at CONNECT_IND TX, the link does not exist yet -- the armed CS still
        //     carries the adv access address, and CS+0x44 reads 0 in sim for every one of
        //     5123 CONNECT_INDs. Switching this constant to 0x44 puts WinOffset=0 on air.
        //   - CS+0x44 becomes the WinOffset at connection *creation*, just after. On silicon
        //     it held the previous attempt's value (24) right up to the creation that
        //     emitted 18, so it is stale at TX time there too -- not merely unpopulated.
        // Read +0x44 only for an established link, never for the initiating activity.
        private const int CsWinOffsetOffset = 0x1E;

        private const int CsRxWindowWideningOffset = 0x1a;  // RX window widening, half-us
        // lld_con_env[] pointer array, indexed by link id (ESP-IDF v5.4.4 blob RAM symbol;
        // does not survive an IDF bump). Same address the HIL anchor probe reads. Now the
        // lldConEnv ctor parameter -- see the constructor comment.
        // Establishment-timeline sampler state (trace-only; see EnsureConEnvTimeline).
        private bool conEnvTimelineRunning;
        private readonly string[] conEnvTimelineLast = new string[2];
        private string initEnvTimelineLast;
        // lld_init_env pointer (initiator/master only); freed once the connection is up.
        // Now the lldInitEnv ctor parameter -- see the constructor comment.
        private const int CsMaxEvtTimeOffset = 0x20;    // MAXEVTIME in 625 us slots (r_lld_con_evt_time_update)
        private const int CsTxDescPtrOffset = 0x1c;     // EM offset of the TX-descriptor ring (dumped live: 0x1400)
        // Link-layer CCM fields, all decoded from r_lld_con_enc_key_load / _rx_enc / _tx_enc.
        private const int CsTxRxControlOffset = 2;
        private const ushort CsRxCryptEnableBit = 1 << 8;
        private const ushort CsTxCryptEnableBit = 1 << 9;
        private const int CsSessionKeyOffset = 44;
        private const int CsIvOffset = 60;
        private const int CsTxCounterOffset = 68;
        private const int CsRxCounterOffset = 74;
        private const int CsPacketCounterLength = 6;
        // RX-descriptor status bit the LL reads as "MIC failure" (r_lld_con_rx 0x4001a214
        // checks it after the CRC/sync error mask and terminates the link).
        private const ushort RxMicErrorBit = 0x10;
        // RX-descriptor status bit for a failed CRC (r_lld_con_rx: `(stat & 8) == 0` gates
        // everything after the anchor re-sync).
        private const ushort RxCrcErrorBit = 0x08;
        private const uint AdvAccessAddress = 0x8E89BED6;

        // Every BLEMedium frame is prefixed with the 4-byte on-air access address.
        private const int AccessAddressLength = 4;

        // LLData sits at PDU offset 14 in a CONNECT_IND (header, len, InitA[6], AdvA[6])
        // and opens with the connection's access address.
        private const int ConnectIndLlDataOffset = 14;

        // reg_blecore VERSION value lld_core_init asserts on (lld.c:324): TYP=0x09 (RW-BLE
        // v9) UPG=0x1B REL=0 BUILD=0. Baked constant 0x09001b00 in libbtdm_app.a.
        private const uint BleCoreVersion = 0x09001b00;

        // Advertising channel reported to BLEMedium (37/38/39).
        private const int AdvChannel37 = 37;

        private readonly uint[] aesKey = new uint[AesKeyWords];
        private uint aesPtr;

        private ulong? receiveTransmitStartHalfUs;
        private uint connAccessAddress;
        // Diagnostic only (C3BLE_TRACE): EM address of the CONNECT_IND TX descriptor's
        // LLData buffer, so the same 22 bytes can be re-read after the initiator event
        // ends and compared with what went on air.
        private ulong connectIndDataPtr;
        private uint rawStatus;
        private uint interruptMask;
        private uint intPrioStored;
        private ulong timeBaseMicroseconds;
        private double clockScale = 1.0;
        private int currentChannel;
        private uint eventTargetSlot;
        private uint fineTarget;
        private uint fineTargetSub;
        private uint grossTarget;
        private ConnRole connRole;
        private int connActivityTag;
        private int connSn;
        private int connNesn;
        // TX descriptor handed to the "MAC" and not yet acknowledged, as a resolved bus
        // address. Single-slot: an unacked descriptor is re-fetched and retransmitted at
        // the next connection event, so there is never more than one outstanding here.
        private ulong pendingTxDesc;
        // Control structure whose ring pendingTxDesc came from, so the ack can advance
        // that ring's CS+0x1c.
        private ulong pendingTxCs;
        // Sealed ciphertext+MIC cached for the descriptor named by pendingTxDesc, so a
        // retransmission of that still-unconfirmed descriptor reuses it instead of
        // re-encrypting under a fresh packet counter (BT Core Vol 6 Part E, 1). Cleared in
        // ConfirmConnTx alongside pendingTxDesc, so it can never survive past the ack that
        // frees the descriptor for reuse by a later, different PDU.
        private ulong txCipherDesc;
        private byte[] txCipherPayload;
        // Header byte of the last connection PDU this node transmitted, for the MD test
        // that decides whether the connection event continues (ShouldContinueConnEvent).
        private byte lastConnTxHeader;
        // Header byte of the last connection PDU received in an armed event: the peer's MD.
        private byte lastConnRxHeader;
        private int connTxRingTraced;
        private int connCryptCsTraced;
        private uint coarseTarget;
        // Set when this node transmits a CONNECT_IND; cleared when the establishment
        // event's packet goes out. See TryConnEventTx for why that one event is offset.
        private bool firstConnEventTxPending;
        // Offset applied to every connection-event slot of the current link, so the whole
        // event grid carries the establishment deferral (see the slot-programming path).
        private ulong connSlotDeferralHalfUs;
        // Where the peer's transmit window 0 opens, and the event grid width, both in
        // half-us; captured when the CONNECT_IND goes out (see the WinOffset block).

        // M3: tracked continuous-scan window state (see OpenScanWindow/CloseScanWindow).
        // The radio event currently running, as handed over on the last push to
        // 0x60031100. Live between its programmed start and start+duration.
        private bool radioEventLive;
        private int radioEventSlot;
        private ulong radioEventCtrlAddr;
        // When the running event began, in half-us. The LL wrote the CS timing fields
        // against this instant before the event ran, so it is the reference any of them
        // has to be re-expressed from when it is read at some later moment.
        private ulong radioEventStartHalfUs;
        private ulong radioEventSeg0Base;
        private ulong radioEventEpoch;
        // A Begin has been scheduled but has not run yet. Together with radioEventLive
        // this decides whether a new push runs now or waits in the queue.
        private bool radioEventScheduled;
        // Pushes handed over while an earlier event was still live or scheduled; the
        // real sch_prog is a hardware FIFO and the LL pipelines into it.
        private readonly Queue<PendingRadioEvent> pendingRadioEvents = new Queue<PendingRadioEvent>();

        private struct PendingRadioEvent
        {
            public int Slot;
            public ulong Seg0Base;
            public ulong OpenHalfUs;
            public ulong DurHalfUs;
            public ulong WideningHalfUs;
        }
        // End instant (half-us) of the latest frame this node put on air; the running
        // event's END is held until it passes (see EndRadioEvent / SendOnMedium).
        private ulong txInFlightUntilHalfUs;

        // Per-INTSTAT-bit arm generation for the one-shot event timers (see ArmEventTimer).
        private readonly Dictionary<uint, ulong> timerEpoch = new Dictionary<uint, ulong>();
        // Per-INTSTAT-bit (target, mask) of the currently-armed-but-unfired comparator, used by
        // ArmEventTimer's anti-storm guard (M3 subsystem 2, §4.2).
        private readonly Dictionary<uint, (uint, uint)> lastArmed = new Dictionary<uint, (uint, uint)>();

        private IValueRegisterField rwbleControl;

        private readonly ConcurrentQueue<KeyValuePair<byte[], IRadio>> rxBuffer;

        // Plain read-back storage for every register offset the behavioural map above does
        // not define (see ReadDoubleWord/WriteDoubleWord). The EM mapping registers the
        // controller programs at init live here.
        private readonly Dictionary<long, uint> windowStorage = new Dictionary<long, uint>();

        // Offsets from base 0x60031000. 0x1C/0x20 decoded from r_rwip_time_get; the INT and
        // deep-sleep offsets are RW9-canonical (RSLxx_Radio) pending M1 fault-loop confirm.
        private enum Registers : long
        {
            Control = 0x000,
            Version = 0x004,
            InterruptControl = 0x00C,
            InterruptStatus = 0x010,
            InterruptRawStatus = 0x014,
            InterruptAcknowledge = 0x018,
            BaseTimeCount = 0x01C,
            FineTimeCount = 0x020,
            EventTarget = 0x024,
            DeepSleepStat = 0x038,
            GrossTimerTarget = 0x0E4,   // r_rwip_timer_10ms handler -> INTCNTL/INTSTAT bit 9 (16-slot units)
            CoarseTimerTarget = 0x0E8,  // r_rwip_timer_hs_set  -> INTCNTL/INTSTAT bit 10
            FineTimerTarget = 0x0EC,    // r_rwip_timer_hus_set -> INTCNTL/INTSTAT bit 11
            FineTimerSub = 0x0F0,       // fine sub-slot target (624 - us)
            AesControl = 0x0B0,         // bit0 = start (r_rwip_aes_encrypt 0x4002f3a2)
            AesKey0 = 0x0B4,            // AESKEY[0..3] at 0x0B4/0x0B8/0x0BC/0x0C0
            AesPtr = 0x0C4,             // EM offset of the plaintext block
            EventProgram = 0x100,       // sch_prog slot hand-off: slot | 0x80000000
            InterruptPriority = 0x2D8,  // priority-dispatch vector read by r_rwble_isr_hack
        }
    }
}
