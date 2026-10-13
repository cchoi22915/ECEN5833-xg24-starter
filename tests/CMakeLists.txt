# Host C tests compile application logic with SDK mocks, without the Arm toolchain.
cmake_minimum_required(VERSION 3.20)
project(series2_host_tests C)
enable_testing()
# Compile every APP_MODE so mode-specific branches are included in the checks.
foreach(mode RANGE 0 3)
  add_executable(app_test_${mode} test_app.c ../firmware/src/app.c ../firmware/src/workload.c)
  # Resolve SDK header names to the small mock interfaces used by test_app.c.
  target_include_directories(app_test_${mode} PRIVATE mocks ../firmware/include)
  target_compile_definitions(app_test_${mode} PRIVATE APP_MODE=${mode})
  target_compile_features(app_test_${mode} PRIVATE c_std_11)
  if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
    # Warnings fail the build, and -UNDEBUG keeps assert checks active.
    target_compile_options(app_test_${mode} PRIVATE -Wall -Wextra -Werror -UNDEBUG)
  endif()
  # Extra command arguments select timer/kit startup failures in the same test binary.
  add_test(NAME mode_${mode}_events COMMAND app_test_${mode})
  add_test(NAME mode_${mode}_failure COMMAND app_test_${mode} failure)
  add_test(NAME mode_${mode}_kit_failure COMMAND app_test_${mode} kit_failure)
endforeach()
# Only demo mode starts the separate LED animation timer.
add_test(NAME mode_3_breath_failure COMMAND app_test_3 breath_failure)
