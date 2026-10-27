/** SPDX-License-Identifier: GPL-3.0-or-later
 * Bounded single-producer prompt receive mailbox. No parsing or effects here.
 * receive() runs in the UART receive context. take()/take_overflow()/reset()
 * MUST run with that UART's receive interrupt excluded. One instance per port.
 */
#pragma once
#include "host_prompt_wire.h"

class HostPromptInbox {
  char receiving_[HostPromptWire::max_length];
  char pending_[HostPromptWire::max_length];
  uint8_t receiving_length_ = 0;
  bool receiving_invalid_ = false;
  volatile bool pending_ready_ = false;
  volatile bool overflow_ = false;
  uint8_t pending_length_ = 0;
  bool pending_invalid_ = false;

  bool candidate() const {
    static const char prefix[] = "M876 V1";
    if (receiving_length_ < sizeof(prefix) - 1) return false;
    for (uint8_t i = 0; i < sizeof(prefix) - 1; ++i)
      if (receiving_[i] != prefix[i]) return false;
    // Reject unsupported versions in main rather than interpreting V10 as V1.
    return receiving_length_ == sizeof(prefix) - 1 || receiving_[sizeof(prefix) - 1] == ' ';
  }

public:
  struct Frame {
    char line[HostPromptWire::max_length];
    uint8_t length;
    bool invalid;
  };

  bool pending() const { return pending_ready_; }

  bool receive(const uint8_t byte) {
    if (byte != '\n') {
      if (receiving_length_ < sizeof(receiving_)) receiving_[receiving_length_++] = char(byte);
      else receiving_invalid_ = true;
      if (byte < 32 || byte > 126) receiving_invalid_ = true;
      return false;
    }
    const bool protocol_frame = candidate();
    if (protocol_frame) {
      if (pending_ready_) overflow_ = true; // preserve the first complete frame
      else {
        for (uint8_t i = 0; i < receiving_length_; ++i) pending_[i] = receiving_[i];
        pending_length_ = receiving_length_;
        pending_invalid_ = receiving_invalid_;
        pending_ready_ = true; // publish last
      }
    }
    receiving_length_ = 0;
    receiving_invalid_ = false;
    return protocol_frame;
  }

  bool take(Frame &out) {
    if (!pending_ready_) return false;
    out.length = pending_length_;
    out.invalid = pending_invalid_;
    for (uint8_t i = 0; i < pending_length_; ++i) out.line[i] = pending_[i];
    pending_ready_ = false;
    return true;
  }

  bool take_overflow() {
    const bool result = overflow_;
    overflow_ = false;
    return result;
  }

  void reset() {
    receiving_length_ = pending_length_ = 0;
    receiving_invalid_ = pending_invalid_ = false;
    pending_ready_ = overflow_ = false;
  }
};
