/* SPDX-License-Identifier: MIT */
#ifndef APP_CONFIG_H
#define APP_CONFIG_H

/* firmware.py --mode selects these values; EM2 remains subject to driver needs. */
#define APP_MODE_AWAKE 0
#define APP_MODE_EM1   1
#define APP_MODE_EM2   2
#define APP_MODE_DEMO  3

/* Override at build time, keeping workload and compiler flags identical. */
#ifndef APP_MODE
#define APP_MODE APP_MODE_DEMO
#endif
#if APP_MODE < APP_MODE_AWAKE || APP_MODE > APP_MODE_DEMO
#error "APP_MODE must be 0 (awake), 1 (EM1), 2 (EM2 permitted), or 3 (display/PWM demo)"
#endif

/* Demo: 1% per step, 0 -> 100 -> 0 in four seconds at the default interval. */
#define APP_LED_BREATH_STEP_MS 20u
#if APP_LED_BREATH_STEP_MS == 0u
#error "APP_LED_BREATH_STEP_MS must be positive"
#endif

/* Work is posted at this interval in milliseconds, in every build mode. */
#define APP_PERIOD_MS 1000u
/* Bound the backlog so an overloaded application reports drops instead of growing. */
#define APP_QUEUE_LIMIT 4u
/* Synthetic CPU work per job; changing this changes the active-time energy cost. */
#define APP_WORK_ITERATIONS 20000u

#endif
