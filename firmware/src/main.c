/* SPDX-License-Identifier: MIT */
#include "sl_system_init.h"
#include "sl_system_process_action.h"
#include "sl_power_manager.h"
#include "app.h"

int main(void)
{
  /* SDK initialization uses the board/components selected in the .slcp recipe. */
  sl_system_init();
  /* Start application timers only after clocks, drivers and services are ready. */
  app_init();

  for (;;) {
    /* Cooperative loop: service SDK work, then consume application events. */
    sl_system_process_action();
    app_process_action();
    /* Sleep until an interrupt; active driver requirements set the allowed mode. */
    /* SDK asks app_is_ok_to_sleep() inside its final sleep decision. */
    sl_power_manager_sleep();
  }
}
