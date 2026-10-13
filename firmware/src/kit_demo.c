/* SPDX-License-Identifier: MIT */
#include "kit_demo.h"
#include "app_config.h"
#include "sl_pwm.h"
#include "sl_pwm_instances.h"

#if APP_MODE == APP_MODE_DEMO
#include <stdio.h>
#include "cu_logo.h"
#include "sl_pwm_init_led0_config.h"
#include "sl_board_control.h"
#include "glib.h"
#include "dmd.h"

/* GLIB draws the picture; DMD transfers the framebuffer to the memory LCD. */
static GLIB_Context_t display;
#endif

sl_status_t kit_demo_init(void)
{
#if APP_MODE == APP_MODE_DEMO
  char pwm_label[24];
  /* Enable the board's display supply/interface before initializing graphics. */
  if (sl_board_enable_display() != SL_STATUS_OK
      || DMD_init(NULL) != DMD_OK
      || GLIB_contextInit(&display) != GLIB_OK) {
    return SL_STATUS_FAIL;
  }
  display.backgroundColor = White;
  display.foregroundColor = Black;
  /* Coordinates are pixels on the 128x128 kit LCD; the 64x64 logo is centered. */
  if (GLIB_clear(&display) != GLIB_OK
      || GLIB_setFont(&display, (GLIB_Font_t *)&GLIB_FontNormal8x8) != GLIB_OK
      || GLIB_drawStringOnLine(&display, "ECEN 5833", 0, GLIB_ALIGN_CENTER, 0, 6, true) != GLIB_OK
      || GLIB_drawStringOnLine(&display, "CU BOULDER", 0, GLIB_ALIGN_CENTER, 0, 20, true) != GLIB_OK
      || GLIB_drawBitmap(&display, 32, 36, CU_LOGO_WIDTH, CU_LOGO_HEIGHT, cu_logo) != GLIB_OK
      || GLIB_setFont(&display, (GLIB_Font_t *)&GLIB_FontNarrow6x8) != GLIB_OK) {
    return SL_STATUS_FAIL;
  }
  /* Read frequency from the SDK-generated PWM configuration, keeping labels consistent. */
  snprintf(pwm_label, sizeof(pwm_label), "%lu Hz / 0-100%%",
           (unsigned long)SL_PWM_LED0_FREQUENCY);
  /* Draw once at startup; duty changes do not require repeated LCD transfers. */
  if (GLIB_drawStringOnLine(&display, "LED0 BREATHING", 0, GLIB_ALIGN_CENTER, 0, 108, true) != GLIB_OK
      || GLIB_drawStringOnLine(&display, pwm_label, 0, GLIB_ALIGN_CENTER, 0, 119, true) != GLIB_OK
      || DMD_updateDisplay() != DMD_OK) {
    return SL_STATUS_FAIL;
  }
  /* The hardware timer drives PWM without an interrupt for every pulse. */
  sl_pwm_set_duty_cycle(&sl_pwm_led0, 0u);
  sl_pwm_start(&sl_pwm_led0);
  return SL_STATUS_OK;
#else
  /* Stopping at 0% would still leave the timer clock enabled; deinitialize it. */
  /* SDK initialization starts the timer; remove it from power comparisons. */
  return sl_pwm_deinit(&sl_pwm_led0);
#endif
}

void kit_demo_set_led_duty(uint8_t duty_percent)
{
  /* Called by app_process_action(), after the short animation ISR posts a flag. */
#if APP_MODE == APP_MODE_DEMO
  sl_pwm_set_duty_cycle(&sl_pwm_led0, duty_percent);
#else
  (void)duty_percent;
#endif
}
