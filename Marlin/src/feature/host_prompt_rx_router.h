/** SPDX-License-Identifier: GPL-3.0-or-later
 * Divert exact unnumbered prompt frames from the ordinary G-code RX ring.
 * The mailbox and emergency parser must still see every original byte.
 */
#pragma once
#include <stdint.h>

class HostPromptRxRouter {
  uint8_t matched_ = 0;
  bool ordinary_ = false, protocol_ = false;
public:
  template<typename Emit> void receive(const uint8_t byte, Emit emit) {
    static const char prefix[] = "M876 V1";
    if (protocol_) {
      if (byte == '\n') { protocol_ = false; matched_ = 0; }
      return;
    }
    if (ordinary_) {
      emit(byte);
      if (byte == '\n') ordinary_ = false;
      return;
    }
    if (matched_ < sizeof(prefix) - 1 && byte == uint8_t(prefix[matched_])) {
      ++matched_;
      return;
    }
    if (matched_ == sizeof(prefix) - 1 && (byte == ' ' || byte == '\n')) {
      protocol_ = byte != '\n';
      matched_ = 0;
      return;
    }
    // This is an ordinary line. Release the at-most-seven held prefix bytes
    // unchanged, then stream the remainder through the existing ring policy.
    for (uint8_t i = 0; i < matched_; ++i) emit(uint8_t(prefix[i]));
    matched_ = 0;
    emit(byte);
    ordinary_ = byte != '\n';
  }
};
