/* Host tests exercise event handoff and failure behavior, not MCU power modes. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include "app.h"
#include "app_config.h"
#include "workload.h"
#include "kit_demo.h"
#include "sl_sleeptimer.h"

/* Save timer callbacks so each test chooses exactly when an interrupt arrives. */
static sl_sleeptimer_timer_callback_t saved_callback;
static sl_sleeptimer_timer_handle_t *saved_timer;
static sl_sleeptimer_timer_callback_t saved_breath_callback;
static sl_sleeptimer_timer_handle_t *saved_breath_timer;
static uint32_t start_status;
static uint32_t breath_start_status;
static uint32_t ticks;
static unsigned atomic_depth;
static unsigned em1_requirements;
static bool inject_on_exit;
static bool inject_breath_on_exit;
static sl_status_t kit_status;
static unsigned duty_updates;
static uint8_t last_duty_percent;

/* Replace kit drivers with observable state; host tests do not draw or drive LEDs. */
sl_status_t kit_demo_init(void) { return kit_status; }
void kit_demo_set_led_duty(uint8_t duty_percent)
{
  assert(APP_MODE == APP_MODE_DEMO && duty_percent <= 100u);
  /* Driver updates must happen in the main loop, outside the atomic handoff. */
  assert(atomic_depth == 0);
  last_duty_percent = duty_percent;
  ++duty_updates;
}

sl_status_t sl_sleeptimer_start_periodic_timer_ms(sl_sleeptimer_timer_handle_t *handle,
    uint32_t period, sl_sleeptimer_timer_callback_t callback,
    void *data, uint8_t priority, uint16_t flags)
{
  assert(data == NULL && priority == 0 && flags == 0);
  /* Initialization starts the workload timer before the optional animation timer. */
  if (saved_callback == NULL) {
    assert(period == APP_PERIOD_MS);
    saved_callback = callback;
    saved_timer = handle;
    return start_status;
  }
  assert(APP_MODE == APP_MODE_DEMO && period == APP_LED_BREATH_STEP_MS);
  assert(handle != saved_timer);
  saved_breath_callback = callback;
  saved_breath_timer = handle;
  return breath_start_status;
}
/* Advance a synthetic clock on reads; this is not elapsed wall-clock time. */
uint32_t sl_sleeptimer_get_tick_count(void) { return ticks++; }
void sl_power_manager_add_em_requirement(sl_power_manager_em_t mode)
{
  assert(mode == SL_POWER_MANAGER_EM1);
  ++em1_requirements;
}
void test_enter_atomic(void) { assert(atomic_depth == 0); ++atomic_depth; }
void test_exit_atomic(void)
{
  /* Inject an event at the handoff boundary to exercise missed-wakeup races. */
  assert(atomic_depth == 1);
  --atomic_depth;
  if (inject_on_exit) {
    inject_on_exit = false;
    saved_callback(saved_timer, NULL);
  }
  if (inject_breath_on_exit) {
    inject_breath_on_exit = false;
    saved_breath_callback(saved_breath_timer, NULL);
  }
}

int main(int argc, char **argv)
{
  /* CTest launches a fresh process for each mode and injected startup failure. */
  bool failure = argc > 1 && strcmp(argv[1], "failure") == 0;
  bool kit_failure = argc > 1 && strcmp(argv[1], "kit_failure") == 0;
  bool breath_failure = argc > 1 && strcmp(argv[1], "breath_failure") == 0;
  start_status = failure ? 1u : SL_STATUS_OK;
  breath_start_status = breath_failure ? 1u : SL_STATUS_OK;
  kit_status = kit_failure ? 1u : SL_STATUS_OK;
  app_init();
  assert(app_stats.mode == APP_MODE);
  assert(em1_requirements == (APP_MODE == APP_MODE_EM1 || APP_MODE == APP_MODE_DEMO ? 1u : 0u));
  if (failure || kit_failure || breath_failure) {
    assert(app_stats.init_status == 1u);
    assert(!app_is_ok_to_sleep());
    assert(app_sleep_on_isr_exit() == SL_POWER_MANAGER_WAKEUP);
    if (kit_failure) {
      assert(saved_callback == NULL);
    }
    if (breath_failure) {
      assert(APP_MODE == APP_MODE_DEMO && saved_breath_callback != NULL);
    } else {
      assert(saved_breath_callback == NULL);
    }
    return 0;
  }

  assert((saved_breath_callback != NULL) == (APP_MODE == APP_MODE_DEMO));
  assert(app_is_ok_to_sleep() == (APP_MODE != APP_MODE_AWAKE));
  /* One posted workload event must prevent sleep until the main loop consumes it. */
  saved_callback(saved_timer, NULL);
  assert(!app_is_ok_to_sleep());
  assert(app_sleep_on_isr_exit() == SL_POWER_MANAGER_WAKEUP);
  app_process_action();
  assert(app_stats.completed_jobs == 1u);
  assert(app_stats.last_result == workload_run(1, APP_WORK_ITERATIONS));
  assert(app_is_ok_to_sleep() == (APP_MODE != APP_MODE_AWAKE));

  /* Interrupt arrives just after the empty-queue check. It remains pending. */
  inject_on_exit = true;
  app_process_action();
  assert(app_stats.completed_jobs == 1u);
  assert(!app_is_ok_to_sleep());
  app_process_action();
  assert(app_stats.completed_jobs == 2u);

  /* Overload is bounded and reported. */
  for (unsigned i = 0; i < APP_QUEUE_LIMIT + 3u; ++i)
    saved_callback(saved_timer, NULL);
  assert(app_stats.dropped_events == 3u);
  for (unsigned i = 0; i < APP_QUEUE_LIMIT + 2u; ++i)
    app_process_action();
  assert(app_stats.completed_jobs == 2u + APP_QUEUE_LIMIT);
  assert(app_stats.timer_events == app_stats.completed_jobs + app_stats.dropped_events);
  assert(atomic_depth == 0);

#if APP_MODE == APP_MODE_DEMO
  uint32_t jobs_before_breathing = app_stats.completed_jobs;
  uint32_t events_before_breathing = app_stats.timer_events;
  /* Two full cycles hit both endpoints and never change duty in the ISR. */
  for (unsigned cycle = 0; cycle < 2u; ++cycle) {
    for (unsigned duty = 1u; duty <= 100u; ++duty) {
      unsigned updates_before = duty_updates;
      saved_breath_callback(saved_breath_timer, NULL);
      assert(duty_updates == updates_before);
      assert(!app_is_ok_to_sleep());
      assert(app_sleep_on_isr_exit() == SL_POWER_MANAGER_WAKEUP);
      app_process_action();
      assert(duty_updates == updates_before + 1u && last_duty_percent == duty);
      assert(app_is_ok_to_sleep());
    }
    for (unsigned duty = 100u; duty > 0u; --duty) {
      saved_breath_callback(saved_breath_timer, NULL);
      app_process_action();
      assert(last_duty_percent == duty - 1u);
    }
  }
  assert(duty_updates == 400u);
  assert(app_stats.completed_jobs == jobs_before_breathing);
  assert(app_stats.timer_events == events_before_breathing);

  /* Late animation ticks are coalesced, with no rapid catch-up burst. */
  for (unsigned i = 0; i < 10u; ++i)
    saved_breath_callback(saved_breath_timer, NULL);
  app_process_action();
  assert(duty_updates == 401u && last_duty_percent == 1u);
  app_process_action();
  assert(duty_updates == 401u && app_is_ok_to_sleep());

  /* A tick after the atomic handoff must prevent sleep and survive to next pass. */
  inject_breath_on_exit = true;
  app_process_action();
  assert(duty_updates == 401u && !app_is_ok_to_sleep());
  assert(app_sleep_on_isr_exit() == SL_POWER_MANAGER_WAKEUP);
  app_process_action();
  assert(duty_updates == 402u && last_duty_percent == 2u);
  assert(app_is_ok_to_sleep());
#else
  assert(duty_updates == 0u);
#endif
  return 0;
}
