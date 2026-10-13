/* Minimal sleep-policy interface. Host tests check decisions, not physical current. */
#ifndef MOCK_PM_H
#define MOCK_PM_H
typedef enum { SL_POWER_MANAGER_EM1 = 1 } sl_power_manager_em_t;
typedef enum { SL_POWER_MANAGER_IGNORE = 1, SL_POWER_MANAGER_SLEEP = 2,
               SL_POWER_MANAGER_WAKEUP = 4 } sl_power_manager_on_isr_exit_t;
/* The test records EM1 requests instead of configuring MCU clocks or regulators. */
void sl_power_manager_add_em_requirement(sl_power_manager_em_t mode);
#endif
