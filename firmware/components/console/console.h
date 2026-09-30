// SPDX-License-Identifier: MIT
// Whole lines on UART0 from any task. ESP-IDF gives each task its own stdout,
// so plain printf from two tasks can interleave mid-line.
#pragma once

// For a line built from several printf calls. Recursive.
void console_lock(void);
void console_unlock(void);

void console_printf(const char *format, ...) __attribute__((format(printf, 1, 2)));
