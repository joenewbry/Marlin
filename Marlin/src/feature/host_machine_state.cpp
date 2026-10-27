/** SPDX-License-Identifier: GPL-3.0-or-later */
#include "../inc/MarlinConfig.h"
#if ENABLED(LLM_MACHINE_STATE)
#if DISABLED(LLM_PROMPT_PROTOCOL) || NUM_AXES != 3 || HOTENDS != 1 || EXTRUDERS != 1 || !HAS_HEATED_BED || !HAS_FAN
  #error "LLM_MACHINE_STATE requires the qualified XYZ, one-extruder prompt profile with bed and fan."
#endif
#include "host_machine_state.h"
#include "../MarlinCore.h"
#include "../gcode/gcode.h"
#include "../gcode/parser.h"
#include "../module/motion.h"
#include "../module/planner.h"
#include "../module/stepper.h"
#include "../module/temperature.h"
#include "../module/fans.h"

HostMachineState host_machine_state_snapshot() {
  HostMachineState state{};
  // Copy only scalar state while interrupts are masked. No serial output,
  // planner synchronization, idle(), settings write or hardware action here.
  CRITICAL_SECTION_START();
  state.uptime = millis();
  state.inactivity[0] = gcode.previous_move_ms;
  state.inactivity[2] = gcode.max_inactive_time;
  #if HAS_DISABLE_IDLE_AXES
    state.inactivity[1] = gcode.stepper_inactive_time;
    state.idle_axes = (TERN0(DISABLE_IDLE_X, true) ? 1 : 0)
      | (TERN0(DISABLE_IDLE_Y, true) ? 2 : 0)
      | (TERN0(DISABLE_IDLE_Z, true) ? 4 : 0)
      | (TERN0(DISABLE_IDLE_E, true) ? 8 : 0);
    if (gcode.stepper_inactive_timeout(state.uptime)) state.timeout_flags |= 1;
  #endif
  if (gcode.stepper_max_timed_out(state.uptime)) state.timeout_flags |= 2;
  state.flags = (marlin.isRunning() ? 1 : 0)
    | (TERN0(HAS_RESUME_CONTINUE, marlin.wait_for_user) ? 2 : 0)
    | (marlin.wait_for_heatup ? 4 : 0) | (planner.leveling_active ? 8 : 0);
  state.homed = motion.axes_homed;
  state.trusted = motion.axes_trusted;
  state.blocks = planner.movesplanned();
  state.tool = motion.extruder;
  for (uint8_t axis = 0; axis < 4; ++axis) {
    state.position[axis] = motion.position[axis];
    if (gcode.axis_is_relative(AxisEnum(axis))) state.relative |= uint8_t(1U << axis);
    if (stepper.axis_is_enabled(AxisEnum(axis))) state.enabled |= uint8_t(1U << axis);
  }
  for (uint8_t axis = 0; axis < 3; ++axis) {
    #if HAS_WORKSPACE_OFFSET
      state.workspace[axis] = motion.workspace_offset[axis];
    #endif
    #if HAS_HOME_OFFSET
      state.home[axis] = motion.home_offset[axis];
    #endif
  }
  state.values[0] = TERN(INCH_MODE_SUPPORT, parser.linear_unit_factor, 1.0f);
  state.values[1] = motion.feedrate_mm_s;
  state.values[2] = motion.feedrate_percentage;
  state.values[3] = planner.flow_percentage[0];
  state.values[4] = fans[0].speed;
  state.values[5] = thermalManager.degHotend(0);
  state.values[6] = thermalManager.degTargetHotend(0);
  state.values[7] = thermalManager.degBed();
  state.values[8] = thermalManager.degTargetBed();
  CRITICAL_SECTION_END();
  return state;
}
#endif
