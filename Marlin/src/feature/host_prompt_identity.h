/**
 * Firmware-owned prompt identity for the optional token-aware host protocol.
 * Copyright (c) 2026
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * State mutations and response validation run in the main loop. The receive
 * parser may snapshot generation() inside its critical section; it must defer
 * requests to the main loop before validating and applying a response.
 */
#pragma once
#include <stdint.h>

enum class HostPromptCheck : uint8_t {
  Ready, NoSession, WrongSession, NoPrompt, NotShown, StalePrompt,
  InvalidChoice, Exhausted, UnsupportedReason, PhysicalActionRequired
};

struct HostPromptSession {
  uint64_t high, low;
  bool operator==(const HostPromptSession &other) const {
    return high == other.high && low == other.low;
  }
};

class HostPromptIdentity {
private:
  HostPromptSession session_ = { 0, 0 };
  volatile uint32_t generation_ = 0;
  uint8_t buttons_ = 0;
  bool active_ = false, shown_ = false, exhausted_ = false;

public:
  bool bound() const { return session_.high || session_.low; }
  HostPromptSession session() const { return session_; }
  uint32_t generation() const { return generation_; }
  uint8_t buttons() const { return buttons_; }
  bool active() const { return active_; }
  bool shown() const { return shown_; }
  bool legacy_accepts(const uint32_t prompt) const {
    return !bound() && active_ && shown_ && !exhausted_ && prompt == generation_;
  }

  // The host must use a fresh random 128-bit session for every connection and
  // firmware boot. Binding never resets generations or clears exhaustion;
  // local wait cleanup must retain the same identity across a rebind.
  bool bind(const HostPromptSession value) {
    if (!(value.high || value.low)) return false;
    if (session_ == value) return true;
    session_ = value;
    return true;
  }

  void begin() {
    active_ = true;
    shown_ = false;
    buttons_ = 0;
    if (generation_ == UINT32_MAX) exhausted_ = true;
    else ++generation_;
  }

  void button() {
    if (!active_ || shown_) return;
    if (buttons_ < UINT8_MAX) ++buttons_;
    else exhausted_ = true;
  }

  void show() { if (active_) shown_ = true; }
  void end() { active_ = shown_ = false; buttons_ = 0; }

  HostPromptCheck check(const HostPromptSession value, const uint32_t prompt,
                        const uint8_t choice) const {
    if (!bound()) return HostPromptCheck::NoSession;
    if (!(session_ == value)) return HostPromptCheck::WrongSession;
    if (exhausted_) return HostPromptCheck::Exhausted;
    if (!active_) return HostPromptCheck::NoPrompt;
    if (!shown_) return HostPromptCheck::NotShown;
    if (prompt != generation_) return HostPromptCheck::StalePrompt;
    if (choice >= buttons_) return HostPromptCheck::InvalidChoice;
    return HostPromptCheck::Ready;
  }
};
