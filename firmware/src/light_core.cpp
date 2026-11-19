#include "light_core.h"

#include <string.h>

namespace pilight {
namespace {

bool literal(const char*& cursor, const char* text) {
    const size_t size = strlen(text);
    if (strncmp(cursor, text, size) != 0) {
        return false;
    }
    cursor += size;
    return true;
}

bool number(const char*& cursor, uint32_t& result) {
    if (*cursor < '0' || *cursor > '9') {
        return false;
    }
    result = 0;
    do {
        const uint32_t digit = static_cast<uint32_t>(*cursor - '0');
        if (result > (UINT32_MAX - digit) / 10u) {
            return false;
        }
        result = result * 10u + digit;
        ++cursor;
    } while (*cursor >= '0' && *cursor <= '9');
    return true;
}

Command parse(const char* line) {
    Command command;
    if (strcmp(line, "HELLO") == 0) {
        command.kind = CommandKind::Hello;
        return command;
    }
    const char* cursor = line;
    if (literal(cursor, "PI1? ")) {
        if (number(cursor, command.sequence) && *cursor == '\0') {
            command.kind = CommandKind::Query;
        }
        return command;
    }
    cursor = line;
    if (!literal(cursor, "PI1 ") || !number(cursor, command.sequence) || *cursor++ != ' ') {
        return command;
    }
    bool found = false;
    for (uint8_t value = 0; value < static_cast<uint8_t>(State::Offline); ++value) {
        const State state = static_cast<State>(value);
        const char* candidate = cursor;
        if (literal(candidate, stateName(state)) && *candidate == ' ') {
            command.state = state;
            cursor = candidate + 1;
            found = true;
            break;
        }
    }
    uint32_t brightness = 0;
    if (found && number(cursor, brightness) && brightness <= kMaxBrightness && *cursor == '\0') {
        command.kind = CommandKind::Set;
        command.brightness = static_cast<uint8_t>(brightness);
    }
    return command;
}

// Integer smoothstep gives a restrained breath without floats or a lookup table.
uint8_t breath(uint32_t elapsed, uint32_t period, uint8_t low, uint8_t high) {
    const uint32_t phase = elapsed % period;
    const uint32_t half = period / 2u;
    const uint32_t ramp = phase <= half ? phase : period - phase;
    const uint32_t x = ramp * 256u / half;
    const uint32_t eased = x * x * (768u - 2u * x) / 65536u;
    return static_cast<uint8_t>(low + (high - low) * eased / 256u);
}

uint8_t dim(uint8_t brightness, uint8_t divisor) {
    if (brightness == 0) {
        return 0;
    }
    const uint8_t result = brightness / divisor;
    return result == 0 ? 1 : result;
}

} // namespace

const char* stateName(State state) {
    switch (state) {
        case State::Working: return "working";
        case State::Waiting: return "waiting";
        case State::Done: return "done";
        case State::Error: return "error";
        case State::Idle: return "idle";
        case State::Offline: return "offline";
    }
    return "offline";
}

bool LineParser::feed(uint8_t byte, Command& command) {
    if (byte == '\n') {
        line_[length_] = '\0';
        command = rejected_ ? Command{} : parse(line_);
        reset();
        return true;
    }
    if (byte < 0x20 || byte > 0x7e || length_ >= sizeof(line_) - 1) {
        rejected_ = true;
    }
    if (!rejected_) {
        line_[length_++] = static_cast<char>(byte);
    }
    return false;
}

void LineParser::reset() {
    length_ = 0;
    rejected_ = false;
}

void Light::advance(uint32_t now) {
    if (online_ && static_cast<uint32_t>(now - heartbeatAt_) >= kHeartbeatTimeoutMs) {
        online_ = false;
        state_ = State::Offline;
        stateAt_ = now;
    }
    if (state_ == State::Done && static_cast<uint32_t>(now - stateAt_) >= 3000u) {
        doneFlashesComplete_ = true;
    }
}

bool Light::set(State state, uint8_t brightness, uint32_t now) {
    if (static_cast<uint8_t>(state) >= static_cast<uint8_t>(State::Offline) || brightness > kMaxBrightness) {
        return false;
    }
    advance(now);
    if (state_ != state) {
        state_ = state;
        stateAt_ = now;
        doneFlashesComplete_ = false;
    }
    online_ = true;
    heartbeatAt_ = now;
    brightness_ = brightness;
    return true;
}

Color Light::color(uint32_t now) const {
    const uint32_t elapsed = now - stateAt_;
    switch (state_) {
        case State::Working:
            return {0, 0, breath(elapsed, 3000, dim(brightness_, 8), brightness_)};
        case State::Waiting: {
            const uint8_t level = breath(elapsed, 1200, dim(brightness_, 8), brightness_);
            return {level, static_cast<uint8_t>(level * 3u / 8u), 0};
        }
        case State::Done: {
            // Three 1 Hz green flashes, then steady. Heartbeats never reset this epoch.
            const bool on = doneFlashesComplete_ || elapsed >= 3000u || elapsed % 1000u < 500u;
            return {0, static_cast<uint8_t>(on ? brightness_ : 0), 0};
        }
        case State::Error: {
            // Two 500 ms red pulses (1 Hz), followed by a 1500 ms dark gap.
            const uint32_t phase = elapsed % 3000u;
            const bool on = phase < 500u || (phase >= 1000u && phase < 1500u);
            return {static_cast<uint8_t>(on ? brightness_ : 0), 0, 0};
        }
        case State::Idle: {
            const uint8_t level = dim(brightness_, 16);
            return {level, level, level};
        }
        case State::Offline: {
            const uint8_t level = breath(elapsed, 5000, 0, dim(brightness_, 6));
            return {level, level, level};
        }
    }
    return {0, 0, 0};
}

} // namespace pilight
