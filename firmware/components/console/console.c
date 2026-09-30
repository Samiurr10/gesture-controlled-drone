// SPDX-License-Identifier: MIT
#include "console.h"

#include <stdarg.h>
#include <stdio.h>
#include <unistd.h>

#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

static SemaphoreHandle_t s_lock;
static StaticSemaphore_t s_lock_storage;
static portMUX_TYPE s_init = portMUX_INITIALIZER_UNLOCKED;

void console_lock(void)
{
    if (!s_lock) {
        taskENTER_CRITICAL(&s_init);
        if (!s_lock) s_lock = xSemaphoreCreateRecursiveMutexStatic(&s_lock_storage);
        taskEXIT_CRITICAL(&s_init);
    }
    xSemaphoreTakeRecursive(s_lock, portMAX_DELAY);
}

void console_unlock(void)
{
    fflush(stdout);
    xSemaphoreGiveRecursive(s_lock);
}

void console_printf(const char *format, ...)
{
    // One write() per line: per-task stdout buffering can still split a printf.
    char line[320];
    va_list args;
    va_start(args, format);
    int length = vsnprintf(line, sizeof(line), format, args);
    va_end(args);
    if (length < 0) return;
    if (length >= (int)sizeof(line)) length = sizeof(line) - 1;
    console_lock();
    fflush(stdout);
    write(fileno(stdout), line, length);
    console_unlock();
}
