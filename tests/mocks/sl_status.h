/* Match the status type/OK value; tests inject a nonzero value to simulate failure. */
#ifndef MOCK_STATUS_H
#define MOCK_STATUS_H
#include <stdint.h>
typedef uint32_t sl_status_t;
#define SL_STATUS_OK 0u
#endif
