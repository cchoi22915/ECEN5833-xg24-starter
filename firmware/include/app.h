/* SPDX-License-Identifier: MIT */
#ifndef APP_H
#define APP_H
#include <stdbool.h>
#include <stdint.h>
#include "sl_power_manager.h"

/* Debugger-visible evidence for the workload; breathing ticks are separate. */
typedef struct {
  uint32_t timer_events;     /* Number of periodic workload interrupts. */
  uint32_t completed_jobs;   /* Jobs actually processed by the main loop. */
  uint32_t dropped_events;   /* Queue overflows: work arrived faster than it ran. */
  uint32_t last_result;      /* Keeps the synthetic calculation observable. */
  uint32_t last_job_ticks;   /* Elapsed sleep-timer ticks, not milliseconds. */
  uint32_t init_status;      /* SL_STATUS_OK is zero; inspect failures here. */
  uint32_t mode;             /* Numeric APP_MODE selected by the build. */
} app_stats_t;

/* Inspect while halted to verify behavior, then disconnect for energy capture. */
extern volatile app_stats_t app_stats;
/* Initialize once after sl_system_init(), then process one main-loop pass. */
void app_init(void);
void app_process_action(void);
/* SDK sleep hooks: pending work or failed startup must keep the CPU awake. */
bool app_is_ok_to_sleep(void);
sl_power_manager_on_isr_exit_t app_sleep_on_isr_exit(void);
#endif
