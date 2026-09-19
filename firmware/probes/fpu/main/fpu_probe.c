// SPDX-License-Identifier: MIT
// Minimal deterministic probe: does single-precision FPU arithmetic execute?
//
// Isolates a simulator fault seen in the hand application, where the first real
// float division inside a FreeRTOS task aborted the engine with
// "Collection was modified; enumeration operation may not execute".
// Each stage prints before and after, so the exact failing operation is visible.
#include <stdio.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static volatile int s_numerator = 1023;
static volatile int s_denominator = 3;
static volatile float s_float_input = 2.5f;

static void stage(const char *name)
{
    printf("{\"type\":\"stage\",\"name\":\"%s\"}\n", name);
    fflush(stdout);
}

static void exercise(const char *context)
{
    stage("int_to_float");
    volatile float a = (float)s_numerator;
    stage("float_divide");
    volatile float b = a / (float)s_denominator;
    stage("float_multiply");
    volatile float c = b * s_float_input;
    stage("float_compare");
    const int larger = (c > 100.0f) ? 1 : 0;
    stage("float_print");
    printf("{\"type\":\"result\",\"context\":\"%s\",\"a\":%.4f,\"b\":%.4f,"
           "\"c\":%.4f,\"larger\":%d}\n", context, (double)a, (double)b,
           (double)c, larger);
    fflush(stdout);
}

static void worker(void *argument)
{
    (void)argument;
    exercise("task");
    printf("{\"type\":\"done\",\"context\":\"task\"}\n");
    fflush(stdout);
    vTaskDelete(NULL);
}

void app_main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    printf("{\"type\":\"ready\",\"fixture\":\"palmpilot-fpu-probe\"}\n");
    fflush(stdout);

    // Stage 1: floats in the main task.
    exercise("app_main");

    // Stage 2: floats in a second FreeRTOS task, which forces the Xtensa
    // coprocessor context to be switched between owners.
    xTaskCreate(worker, "fpu_worker", 4096, NULL, 6, NULL);
    vTaskDelay(pdMS_TO_TICKS(200));
    printf("{\"type\":\"done\",\"context\":\"app_main\"}\n");
    fflush(stdout);
}
