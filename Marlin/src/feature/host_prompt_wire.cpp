/** SPDX-License-Identifier: GPL-3.0-or-later */
#include "../inc/MarlinConfig.h"
#if ENABLED(LLM_PROMPT_PROTOCOL)
#include "host_actions.h"
#include "host_prompt_inbox.h"
#include "../MarlinCore.h"

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
