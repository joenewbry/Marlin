/** SPDX-License-Identifier: GPL-3.0-or-later */
#include "../inc/MarlinConfig.h"
#if ENABLED(LLM_PROMPT_PROTOCOL)
#include "host_actions.h"
#include "host_prompt_inbox.h"
#include "../MarlinCore.h"
#if ENABLED(LLM_MACHINE_STATE)
  #include "host_machine_state.h"
  #include <string.h>
#endif

volatile bool host_prompt_token_mode = false, host_prompt_protocol_busy = false;
static HostPromptInbox inbox;
static bool processing = false, have_receipt = false;
static HostPromptCommand previous;
static uint8_t previous_result = 0;

void host_prompt_receive_byte(const uint8_t byte) {
  if (inbox.receive(byte)) host_prompt_protocol_busy = true;
}

struct PromptProcessingGuard {
  ~PromptProcessingGuard() {
    CRITICAL_SECTION_START();
    host_prompt_protocol_busy = inbox.pending();
    processing = false;
    CRITICAL_SECTION_END();
  }
};

static void hex_value(const uint64_t value, const uint8_t digits) {
  for (int8_t digit = digits - 1; digit >= 0; --digit) {
    const uint8_t nibble = (value >> (digit * 4)) & 15;
    SERIAL_CHAR(nibble < 10 ? '0' + nibble : 'a' + nibble - 10);
  }
}

#if ENABLED(LLM_MACHINE_STATE)
static uint32_t machine_state_sequence = 0;
static void state_values(const float *values, const uint8_t count) {
  static_assert(sizeof(float) == sizeof(uint32_t), "State wire requires binary32 float");
  for (uint8_t i = 0; i < count; ++i) {
    uint32_t bits;
    memcpy(&bits, values + i, sizeof(bits));
    hex_value(bits, 8);
  }
}

static void machine_state_receipt(const uint32_t request) {
  if (!request || !host_prompt_identity.bound() || machine_state_sequence == UINT32_MAX) return;
  const HostPromptSession session = host_prompt_identity.session();
  const HostMachineState state = host_machine_state_snapshot();
  ++machine_state_sequence; // Saturate rather than wrap an old observation ID.
  PORT_REDIRECT(SerialMask::All);
  SERIAL_ECHOPGM("//llmstate:v2 Q"); hex_value(request, 8);
  SERIAL_ECHOPGM(" T"); hex_value(session.high, 16); hex_value(session.low, 16);
  SERIAL_ECHOPGM(" N"); hex_value(machine_state_sequence, 8);
  SERIAL_ECHOPGM(" U"); hex_value(state.uptime, 8);
  SERIAL_ECHOPGM(" F"); hex_value(state.flags, 2);
  SERIAL_ECHOPGM(" H"); hex_value(state.homed, 2);
  SERIAL_ECHOPGM(" K"); hex_value(state.trusted, 2);
  SERIAL_ECHOPGM(" E"); hex_value(state.enabled, 2);
  SERIAL_ECHOPGM(" B"); hex_value(state.blocks, 2);
  SERIAL_ECHOPGM(" R"); hex_value(state.relative, 2);
  SERIAL_ECHOPGM(" A"); hex_value(state.tool, 2);
  SERIAL_ECHOPGM(" P"); state_values(state.position, 4);
  SERIAL_ECHOPGM(" O"); state_values(state.workspace, 3);
  SERIAL_ECHOPGM(" D"); state_values(state.home, 3);
  SERIAL_ECHOPGM(" V"); state_values(state.values, 9);
  SERIAL_ECHOPGM(" I");
  for (uint8_t i = 0; i < 3; ++i) hex_value(state.inactivity[i], 8);
  SERIAL_ECHOPGM(" C"); hex_value(state.idle_axes, 2);
  SERIAL_ECHOPGM(" J"); hex_value(state.timeout_flags, 2);
  SERIAL_EOL();
}
#endif

// Fixed-format receipt, separate from ordinary G-code ok. C00 is handler
// acceptance only; the snapshot describes current prompt state, not motion.
static void receipt(const uint32_t request, const uint8_t result, const bool duplicate=false) {
  PORT_REDIRECT(SerialMask::All);
  SERIAL_ECHOPGM("//llm:v1 Q"); hex_value(request, 8);
  SERIAL_ECHOPGM(" C"); hex_value(result, 2);
  SERIAL_ECHOPGM(" D"); SERIAL_CHAR(duplicate ? '1' : '0');
  SERIAL_ECHOPGM(" T");
  const HostPromptSession session = host_prompt_identity.session();
  hex_value(session.high, 16); hex_value(session.low, 16);
  SERIAL_ECHOPGM(" P"); hex_value(host_prompt_identity.generation(), 8);
  SERIAL_ECHOPGM(" A"); SERIAL_CHAR(host_prompt_identity.active() ? '1' : '0');
  SERIAL_ECHOPGM(" H"); SERIAL_CHAR(host_prompt_identity.shown() ? '1' : '0');
  SERIAL_ECHOPGM(" B"); hex_value(host_prompt_identity.buttons(), 2);
  SERIAL_ECHOPGM(" R"); hex_value(host_prompt_wire_reason(), 2);
  SERIAL_ECHOPGM(" W"); SERIAL_CHAR(TERN0(HAS_RESUME_CONTINUE, marlin.wait_for_user) ? '1' : '0');
  SERIAL_EOL();
}

static bool same_command(const HostPromptCommand &a, const HostPromptCommand &b) {
  return a.kind == b.kind && a.session == b.session && a.request == b.request
    && a.prompt == b.prompt && a.choice == b.choice;
}

void host_prompt_wire_process() {
  if (processing) return; // recovery handlers may recursively service idle()
  processing = true;
  PromptProcessingGuard guard;
  HostPromptInbox::Frame frame;
  bool available, overflow;
  {
    CRITICAL_SECTION_START();
    available = inbox.take(frame);
    overflow = inbox.take_overflow();
    CRITICAL_SECTION_END();
  }
  if (overflow) receipt(0, 0x81);
  if (!available) { return; }
  HostPromptCommand command;
  if (frame.invalid || !HostPromptWire::parse(frame.line, frame.length, command)) {
    receipt(0, 0x80);
    return;
  }
  if (command.kind == HostPromptCommandKind::Inspect) {
    receipt(command.request, 0);
    #if ENABLED(LLM_MACHINE_STATE)
      machine_state_receipt(command.request);
    #endif
    return;
  }
  // One binding per boot. Do not let a delayed bind switch authority back to
  // an old connection. Reconnection/rebinding requires separate qualification.
  if (host_prompt_identity.bound() && !(host_prompt_identity.session() == command.session)) {
    receipt(command.request, uint8_t(HostPromptCheck::WrongSession));
    return;
  }
  if (!host_prompt_identity.bound() && command.kind == HostPromptCommandKind::Respond) {
    receipt(command.request, uint8_t(HostPromptCheck::NoSession));
    return;
  }
  if (have_receipt && command.request <= previous.request) {
    const bool duplicate = same_command(command, previous);
    receipt(command.request, duplicate ? previous_result : command.request == previous.request ? 0x82 : 0x83, duplicate);
    return;
  }
  uint8_t result;
  if (command.kind == HostPromptCommandKind::Bind) {
    host_prompt_identity.bind(command.session);
    host_prompt_token_mode = true;
    result = 0;
  }
  else result = uint8_t(host_token_response(command.session, command.prompt, command.choice));
  previous = command;
  previous_result = result;
  have_receipt = true;
  receipt(command.request, result);
}
#endif
