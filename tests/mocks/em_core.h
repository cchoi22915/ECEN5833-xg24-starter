/* Instrument critical sections in test_app.c; this does not mask real interrupts. */
#ifndef MOCK_CORE_H
#define MOCK_CORE_H
void test_enter_atomic(void);
void test_exit_atomic(void);
/* Preserve SDK macro names so the same app.c compiles for host tests and the MCU. */
#define CORE_DECLARE_IRQ_STATE
#define CORE_ENTER_ATOMIC() test_enter_atomic()
#define CORE_EXIT_ATOMIC() test_exit_atomic()
#endif
