# firmware.py passes the numeric mode; use the LCD/PWM demo when none is specified.
set(APP_MODE "3" CACHE STRING "0=awake, 1=EM1, 2=EM2 permitted, 3=display/PWM demo")
if(NOT APP_MODE MATCHES "^[0123]$")
  message(FATAL_ERROR "APP_MODE must be 0, 1, 2, or 3")
endif()
# SLC's target carries the same mode definition into application compilation.
target_compile_definitions(slc PUBLIC "APP_MODE=${APP_MODE}")
