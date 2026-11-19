#pragma once

#include <stddef.h>
#include <stdint.h>

namespace pilight {

constexpr size_t kMaxLineBytes = 96; // Includes LF.
constexpr uint32_t kHeartbeatTimeoutMs = 15000;
constexpr uint8_t kDefaultBrightness = 48;
constexpr uint8_t kMaxBrightness = 128;

enum class State : uint8_t { Working, Waiting, Done, Error, Idle, Offline };
enum class CommandKind : uint8_t { Invalid, Hello, Query, Set };

struct Command {
    CommandKind kind = CommandKind::Invalid;
    uint32_t sequence = 0;
    State state = State::Idle;
    uint8_t brightness = kDefaultBrightness;
};

struct Color {
    uint8_t red;
    uint8_t green;
    uint8_t blue;
};

const char* stateName(State state);

// One bounded buffer; a rejected physical line is discarded through its LF.
class LineParser {
public:
    bool feed(uint8_t byte, Command& command);
    void reset();

private:
    char line_[kMaxLineBytes] = {};
    size_t length_ = 0;
    bool rejected_ = false;
};

class Light {
public:
    void advance(uint32_t now);
    bool set(State state, uint8_t brightness, uint32_t now);
    State state() const { return state_; }
    uint8_t brightness() const { return brightness_; }
    Color color(uint32_t now) const;

private:
    State state_ = State::Offline;
    uint8_t brightness_ = kDefaultBrightness;
    bool online_ = false;
    bool doneFlashesComplete_ = false;
    uint32_t heartbeatAt_ = 0;
    uint32_t stateAt_ = 0;
};

} // namespace pilight
