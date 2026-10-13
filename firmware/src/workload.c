/* SPDX-License-Identifier: MIT */
#include "workload.h"

/* Deterministic synthetic work. This is not a sensor measurement or RNG API. */
uint32_t workload_run(uint32_t seed, uint32_t iterations)
{
  /* Fixed-width unsigned arithmetic gives repeatable wrapping across host/MCU builds. */
  uint32_t value = seed;
  for (uint32_t i = 0; i < iterations; ++i) {
    value ^= value << 13;
    value ^= value >> 17;
    value ^= value << 5;
    value += 0x9e3779b9u + i;
  }
  /* app.c stores this result in volatile stats, keeping the work observable. */
  return value;
}
