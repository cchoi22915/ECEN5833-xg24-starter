/* SPDX-License-Identifier: MIT */
#ifndef KIT_DEMO_H
#define KIT_DEMO_H
#include <stdint.h>
#include "sl_status.h"

/* Keep kit-only display/PWM details behind this interface when adding drivers. */
/* Show the LCD/PWM demo, or turn the kit outputs off in comparison modes. */
sl_status_t kit_demo_init(void);
/* Duty is percent, not a timer compare count; the caller supplies 0 through 100. */
/* Demo-only duty update; call from the main loop, with a value from 0 to 100. */
void kit_demo_set_led_duty(uint8_t duty_percent);
#endif
