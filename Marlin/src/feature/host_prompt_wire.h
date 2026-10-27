/** SPDX-License-Identifier: GPL-3.0-or-later
 * Experimental versioned prompt wire grammar. Parsing has no machine effects.
 * Call in main context after a bounded receive mailbox has delivered a line.
 */
#pragma once
#include "host_prompt_identity.h"
#include <stddef.h>

enum class HostPromptCommandKind : uint8_t { Inspect, Bind, Respond };
struct HostPromptCommand {
  HostPromptCommandKind kind = HostPromptCommandKind::Inspect;
  HostPromptSession session = {0, 0};
  uint32_t request = 0, prompt = 0;
  uint8_t choice = 0;
};

class HostPromptWire {
  const char *line_;
  const size_t size_;
  size_t offset_ = 0;

  bool literal(const char *text) {
    while (*text) {
      if (offset_ == size_ || line_[offset_++] != *text++) return false;
    }
    return true;
  }
  bool hex(const uint8_t digits, uint64_t &value) {
    value = 0;
    for (uint8_t i = 0; i < digits; ++i) {
      if (offset_ == size_) return false;
      const char c = line_[offset_++];
      const int8_t nibble = c >= '0' && c <= '9' ? c - '0'
        : c >= 'a' && c <= 'f' ? c - 'a' + 10 : -1;
      if (nibble < 0) return false;
      value = (value << 4) | uint8_t(nibble);
    }
    return true;
  }
  HostPromptWire(const char *line, const size_t size) : line_(line), size_(size) {}

public:
  // Longest command is 65 bytes before LF. No whitespace normalization,
  // comments, numbered envelopes, signs, uppercase hex, or optional fields.
  static constexpr size_t max_length = 65;
  static bool parse(const char *line, const size_t size, HostPromptCommand &out) {
    if (!line || size > max_length) return false;
    HostPromptWire parser(line, size);
    HostPromptCommand candidate;
    if (!parser.literal("M876 V1 ") || parser.offset_ == size) return false;
    const char kind = line[parser.offset_++];
    if (kind == 'I') candidate.kind = HostPromptCommandKind::Inspect;
    else if (kind == 'B' || kind == 'R') {
      candidate.kind = kind == 'B' ? HostPromptCommandKind::Bind : HostPromptCommandKind::Respond;
      if (!parser.hex(16, candidate.session.high) || !parser.hex(16, candidate.session.low)
          || !(candidate.session.high || candidate.session.low)) return false;
      if (kind == 'R') {
        uint64_t prompt, choice;
        if (!parser.literal(" P") || !parser.hex(8, prompt) || !prompt
            || !parser.literal(" S") || !parser.hex(2, choice)) return false;
        candidate.prompt = uint32_t(prompt);
        candidate.choice = uint8_t(choice);
      }
    }
    else return false;
    uint64_t request;
    if (!parser.literal(" Q") || !parser.hex(8, request) || !request
        || parser.offset_ != size) return false;
    candidate.request = uint32_t(request);
    out = candidate; // malformed input never partly updates caller state
    return true;
  }
};

// One instance per input stream; never share partial frames between ports.
// This decoder parses in the caller's context. Firmware integration must feed
// it from main context or defer a complete bounded frame before parsing.
class HostPromptFramer {
  char line_[HostPromptWire::max_length];
  uint8_t length_ = 0;
  bool discarded_ = false;
public:
  enum class Result : uint8_t { Incomplete, Command, Rejected };
  void reset() { length_ = 0; discarded_ = false; }
  Result feed(const uint8_t byte, HostPromptCommand &out) {
    if (byte == '\n') {
      const bool valid = !discarded_ && HostPromptWire::parse(line_, length_, out);
      reset();
      return valid ? Result::Command : Result::Rejected;
    }
    if (!discarded_) {
      if (length_ == sizeof(line_) || byte < 32 || byte > 126) discarded_ = true;
      else line_[length_++] = char(byte);
    }
    return Result::Incomplete;
  }
};
