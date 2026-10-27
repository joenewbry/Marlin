/** SPDX-License-Identifier: GPL-3.0-or-later
 * Read-only controller state, not physical readiness or a completion barrier.
 */
#pragma once
#include <stdint.h>

struct HostMachineState {
  uint32_t uptime;
  uint8_t flags, homed, trusted, enabled, blocks, relative, tool;
  float position[4], workspace[3], home[3];
  // Unit factor, feedrate mm/s, feed/flow %, fan PWM, nozzle actual/target,
  // bed actual/target. Values are controller variables, not measurements.
  float values[9];
  // Raw uint32 millisecond counters: activity origin, M84 interval, M85 interval.
  // Predicate flags describe sampled controller logic, never actual shutdown.
  uint32_t inactivity[3];
  uint8_t idle_axes, timeout_flags;
};

HostMachineState host_machine_state_snapshot();
