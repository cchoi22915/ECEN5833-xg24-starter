/* SPDX-License-Identifier: MIT */
#ifndef WORKLOAD_H
#define WORKLOAD_H
#include <stdint.h>
/* Reproducible CPU workload: seed selects the result, iterations sets the cost. */
/* Replace this function and its app.c call with your project's processing. */
uint32_t workload_run(uint32_t seed, uint32_t iterations);
#endif
