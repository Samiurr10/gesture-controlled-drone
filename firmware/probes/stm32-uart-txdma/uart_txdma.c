// SPDX-License-Identifier: MIT
// STM32F4 USART TX by DMA, from an idle transmitter (NUCLEO-F446RE; the
// registers used are the same on the NUCLEO-F401RE).
//
// USART2 (PA2, the ST-LINK virtual COM port) at 115200 from the 16 MHz HSI.
// DMA1 stream 6 channel 4 is USART2_TX. Two ways firmware arms a TX DMA:
//   A: DMAT set while TXE=1, then the stream enabled   (ArduPilot/ChibiOS)
//   B: the stream enabled, then DMAT set              (STM32Cube HAL)
// Either way the USART requests a transfer whenever TXE is set (RM0390), so
// the stream must run to NDTR=0 and set TCIF (simantic-core#635). Status lines are written by the
// CPU, so they appear even when the DMA does not.
#include <stdint.h>

#define REG(addr) (*(volatile uint32_t *)(addr))
#define RCC_AHB1ENR REG(0x40023830)
#define RCC_APB1ENR REG(0x40023840)
#define GPIOA_MODER REG(0x40020000)
#define GPIOA_AFRL REG(0x40020020)
#define USART2_SR REG(0x40004400)
#define USART2_DR REG(0x40004404)
#define USART2_BRR REG(0x40004408)
#define USART2_CR1 REG(0x4000440C)
#define USART2_CR3 REG(0x40004414)
#define DMA1_HISR REG(0x40026004)
#define DMA1_HIFCR REG(0x4002600C)
#define S6CR REG(0x400260A0)
#define S6NDTR REG(0x400260A4)
#define S6PAR REG(0x400260A8)
#define S6M0AR REG(0x400260AC)

#define SR_TXE (1u << 7)
#define SR_TC (1u << 6)
#define CR3_DMAT (1u << 7)
#define HISR_S6_ALL (0x3Du << 16)      // FEIF6 DMEIF6 TEIF6 HTIF6 TCIF6
#define HISR_TCIF6 (1u << 21)
#define HISR_TEIF6 (1u << 19)
#define TIMEOUT_SPINS 2000000u          // well over 100 ms at 16 MHz

static void put(const char *s)
{
    for (; *s; ++s) {
        while (!(USART2_SR & SR_TXE)) {
        }
        USART2_DR = (uint8_t)*s;
    }
    while (!(USART2_SR & SR_TC)) {
    }
}

static void put_u32(uint32_t v)
{
    char buf[11];
    int i = 10;
    buf[i] = 0;
    do {
        buf[--i] = (char)('0' + v % 10);
        v /= 10;
    } while (v);
    put(&buf[i]);
}

static void arm_stream(const char *msg, uint32_t len)
{
    S6CR = 0;
    while (S6CR & 1u) {
    }
    DMA1_HIFCR = HISR_S6_ALL;
    S6PAR = (uint32_t)&USART2_DR;
    S6M0AR = (uint32_t)msg;
    S6NDTR = len;
    // CHSEL=4, MINC, DIR=memory-to-peripheral, then EN.
    S6CR = (4u << 25) | (1u << 10) | (1u << 6);
    S6CR |= 1u;
}

// Returns 1 when the stream completed without error before the timeout.
static int wait_stream(void)
{
    for (uint32_t i = 0; i < TIMEOUT_SPINS; ++i) {
        uint32_t hisr = DMA1_HISR;
        if (hisr & HISR_TEIF6) return 0;
        if (hisr & HISR_TCIF6) return 1;
    }
    return 0;
}

static int run_case(const char *name, int dmat_first, const char *msg, uint32_t len)
{
    while (!(USART2_SR & SR_TC)) {
    }
    USART2_CR3 &= ~CR3_DMAT;
    if (dmat_first) {
        USART2_CR3 |= CR3_DMAT;        // transmitter idle: TXE=1 already
        arm_stream(msg, len);
    } else {
        arm_stream(msg, len);
        USART2_CR3 |= CR3_DMAT;
    }
    int ok = wait_stream() && S6NDTR == 0;
    uint32_t left = S6NDTR;
    S6CR = 0;
    USART2_CR3 &= ~CR3_DMAT;
    while (!(USART2_SR & SR_TC)) {
    }
    put("\r\nTXDMA ");
    put(ok ? "PASS " : "FAIL ");
    put(name);
    put(" ndtr=");
    put_u32(left);
    put("\r\n");
    return ok;
}

static const char msg_a[] = "TXDMA: case A sent by DMA\r\n";
static const char msg_b[] = "TXDMA: case B sent by DMA\r\n";

int main(void)
{
    RCC_AHB1ENR |= (1u << 0) | (1u << 21);   // GPIOA, DMA1
    RCC_APB1ENR |= (1u << 17);               // USART2
    (void)RCC_APB1ENR;
    GPIOA_MODER = (GPIOA_MODER & ~(3u << 4)) | (2u << 4);    // PA2 alternate
    GPIOA_AFRL = (GPIOA_AFRL & ~(0xFu << 8)) | (7u << 8);    // AF7 USART2_TX
    USART2_BRR = (8u << 4) | 11u;            // 16 MHz / 115200 = 8.6875
    USART2_CR1 = (1u << 13) | (1u << 3);     // UE, TE

    put("\r\nTXDMA: boot\r\n");
    int failures = 0;
    failures += !run_case("dmat_then_enable", 1, msg_a, sizeof(msg_a) - 1);
    failures += !run_case("enable_then_dmat", 0, msg_b, sizeof(msg_b) - 1);
    put("RESULT: ");
    put(failures ? "FAIL failures=" : "PASS failures=");
    put_u32((uint32_t)failures);
    put("\r\n");
    for (;;) {
    }
}

// Minimal vector table and reset handler: no HAL, no libc.
extern uint32_t _sidata, _sdata, _edata, _sbss, _ebss, _estack;

void Reset_Handler(void)
{
    for (uint32_t *src = &_sidata, *dst = &_sdata; dst < &_edata;) *dst++ = *src++;
    for (uint32_t *dst = &_sbss; dst < &_ebss;) *dst++ = 0;
    main();
}

static void Default_Handler(void)
{
    for (;;) {
    }
}

__attribute__((section(".isr_vector"), used))
static void (*const vectors[16])(void) = {
    (void (*)(void))&_estack, Reset_Handler, Default_Handler, Default_Handler,
    Default_Handler, Default_Handler, Default_Handler, 0, 0, 0, 0,
    Default_Handler, Default_Handler, 0, Default_Handler, Default_Handler,
};
