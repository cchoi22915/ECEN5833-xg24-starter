/* Timer registration is faked; test_app.c explicitly invokes saved callbacks. */
#ifndef MOCK_TIMER_H
#define MOCK_TIMER_H
#include <stddef.h>
#include <stdint.h>
#include "sl_status.h"
/* Only handle identity matters to these tests, not the SDK's internal timer fields. */
typedef struct { unsigned unused; } sl_sleeptimer_timer_handle_t;
typedef void (*sl_sleeptimer_timer_callback_t)(sl_sleeptimer_timer_handle_t *, void *);
sl_status_t sl_sleeptimer_start_periodic_timer_ms(sl_sleeptimer_timer_handle_t *,
    uint32_t, sl_sleeptimer_timer_callback_t, void *, uint8_t, uint16_t);
uint32_t sl_sleeptimer_get_tick_count(void);
#endif
