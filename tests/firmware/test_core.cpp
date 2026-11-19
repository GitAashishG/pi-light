#include "light_core.h"

#include <assert.h>
#include <stdint.h>
#include <initializer_list>
#include <stdio.h>
#include <string>

using pilight::Color;
using pilight::Command;
using pilight::CommandKind;
using pilight::Light;
using pilight::LineParser;
using pilight::State;

namespace {

Command line(LineParser& parser, const std::string& bytes) {
    Command command;
    size_t frames = 0;
    for (unsigned char byte : bytes) {
        if (parser.feed(byte, command)) {
            ++frames;
        }
    }
    assert(frames == 1);
    return command;
}

bool equal(Color a, Color b) {
    return a.red == b.red && a.green == b.green && a.blue == b.blue;
}

void parserTests() {
    LineParser parser;
    assert(line(parser, "HELLO\n").kind == CommandKind::Hello);
    Command command = line(parser, "PI1? 4294967295\n");
    assert(command.kind == CommandKind::Query && command.sequence == UINT32_MAX);
    command = line(parser, "PI1 0 working 0\n");
    assert(command.kind == CommandKind::Set && command.sequence == 0);
    assert(command.state == State::Working && command.brightness == 0);
    for (unsigned value = 0; value < static_cast<unsigned>(State::Offline); ++value) {
        const State state = static_cast<State>(value);
        command = line(parser, std::string("PI1 7 ") + pilight::stateName(state) + " 128\n");
        assert(command.kind == CommandKind::Set && command.state == state && command.brightness == 128);
    }
    const char* invalid[] = {
        "\n", "HELLO \n", "HELLO\r\n", "hello\n", "PI1?\n", "PI1? -1\n", "PI1? +1\n",
        "PI1? 4294967296\n", "PI1? 1 \n", "PI1?  1\n", "PI1? 1 garbage\n",
        "PI1 1 offline 48\n", "PI1 1 WORKING 48\n", "PI1 1 done 129\n", "PI1 1 done -1\n",
        "PI1 1 done 4294967296\n", "PI1 4294967296 done 48\n", "PI1 1 done\n", "PI1 1done 48\n",
        "PI1 1  done 48\n", "PI1 1 done  48\n", "PI1 1 done 48 \n", "PI1 1 done 48\r\n",
        "PI1\t1 done 48\n", " PI1 1 done 48\n", "PI1 1 done 48 extra\n"
    };
    for (const char* frame : invalid) {
        assert(line(parser, frame).kind == CommandKind::Invalid);
    }
    assert(line(parser, std::string("PI1 1 done 48\0junk\n", 19)).kind == CommandKind::Invalid);
    for (unsigned byte = 0; byte <= 255; ++byte) {
        if (byte == '\n' || (byte >= 0x20 && byte <= 0x7e)) {
            continue;
        }
        assert(line(parser, std::string("HELLO") + static_cast<char>(byte) + "\n").kind == CommandKind::Invalid);
    }
    // Exactly 96 physical bytes is accepted; 97 bytes is rejected even if the
    // numeric value is otherwise valid. Leading zeroes are legal uint32 input.
    command = line(parser, std::string("PI1? ") + std::string(90, '0') + "\n");
    assert(command.kind == CommandKind::Query && command.sequence == 0);
    assert(line(parser, std::string("PI1? ") + std::string(91, '0') + "\n").kind == CommandKind::Invalid);
    assert(line(parser, std::string(10000, 'x') + "HELLO\n").kind == CommandKind::Invalid);
    assert(line(parser, "HELLO\n").kind == CommandKind::Hello);
    Command partial;
    assert(!parser.feed('H', partial));
    assert(!parser.feed('E', partial));
    parser.reset(); // Reconnection must not splice two connections' fragments.
    assert(line(parser, "HELLO\n").kind == CommandKind::Hello);
    size_t frames = 0;
    const std::string burst = "HELLO\nPI1 8 waiting 48\nPI1? 9\ninvalid\n";
    for (unsigned char byte : burst) {
        frames += parser.feed(byte, partial) ? 1 : 0;
    }
    assert(frames == 4 && partial.kind == CommandKind::Invalid);
}

void heartbeatTests() {
    Light light;
    assert(light.state() == State::Offline && light.brightness() == 48);
    assert(light.set(State::Working, 48, 100));
    light.advance(15099);
    assert(light.state() == State::Working);
    light.advance(15100);
    assert(light.state() == State::Offline);
    assert(light.set(State::Done, 48, 16000));
    assert(light.set(State::Done, 48, 30000));
    light.advance(44999);
    assert(light.state() == State::Done);
    light.advance(45000);
    assert(light.state() == State::Offline);

    assert(!light.set(State::Offline, 48, 45001));
    assert(!light.set(static_cast<State>(255), 48, 45001));
    assert(!light.set(State::Idle, 129, 45001));
    assert(light.state() == State::Offline && light.brightness() == 48);

    // This is the dispatch rule used by application.cpp. Read-only or invalid
    // frames do not reach Light::set and therefore cannot renew the watchdog.
    LineParser parser;
    assert(light.set(State::Done, 48, 50000));
    for (const char* frame : {"HELLO\n", "PI1? 1\n", "PI1 1 idle 129\n", "PI1 1 offline 48\n"}) {
        const Command command = line(parser, frame);
        if (command.kind == CommandKind::Set) {
            light.set(command.state, command.brightness, 64999);
        }
    }
    light.advance(65000);
    assert(light.state() == State::Offline);

    Light wrapped;
    const uint32_t start = UINT32_MAX - 1000u;
    assert(wrapped.set(State::Working, 48, start));
    wrapped.advance(start + 14999u);
    assert(wrapped.state() == State::Working);
    wrapped.advance(start + 15000u);
    assert(wrapped.state() == State::Offline);
    assert(wrapped.set(State::Idle, 48, start + 15001u));
    wrapped.advance(start + 30000u);
    assert(wrapped.state() == State::Idle);
    wrapped.advance(start + 30001u);
    assert(wrapped.state() == State::Offline);
}

void animationTests() {
    Light light;
    assert(light.set(State::Done, 48, 100));
    assert(light.color(100).green == 48);
    assert(light.color(599).green == 48);
    assert(light.color(600).green == 0);
    assert(light.set(State::Done, 64, 800)); // Brightness/heartbeat must not restart flashes.
    assert(light.color(800).green == 0);
    assert(light.color(1100).green == 64);
    light.advance(3100);
    assert(light.color(3100).green == 64);
    assert(light.set(State::Done, 48, 3600));
    assert(light.color(3650).green == 48);
    // A completed transition stays latched even after the epoch subtraction wraps.
    assert(light.color(99).green == 48);
    assert(light.set(State::Working, 48, 4000));
    assert(light.set(State::Done, 48, 5000));
    assert(light.color(5500).green == 0);
    light.advance(20000);
    assert(light.state() == State::Offline);
    assert(light.set(State::Done, 48, 20000));
    assert(light.color(20500).green == 0);

    Light wrapped;
    const uint32_t start = UINT32_MAX - 250u;
    assert(wrapped.set(State::Done, 48, start));
    assert(wrapped.color(start + 499u).green == 48);
    assert(wrapped.color(start + 500u).green == 0);
    wrapped.advance(start + 3000u);
    assert(wrapped.color(start + 3500u).green == 48);

    Light idle;
    assert(idle.set(State::Idle, 48, 0));
    assert(equal(idle.color(0), Color{3, 3, 3}));
    assert(equal(idle.color(0), idle.color(5000)));
    idle.advance(15000);
    assert(idle.state() == State::Offline);
    assert(!equal(idle.color(15000), idle.color(17500)));

    Light error;
    assert(error.set(State::Error, 48, 0));
    for (uint32_t t : {0u, 499u, 1000u, 1499u, 3000u}) {
        assert(equal(error.color(t), Color{48, 0, 0}));
    }
    for (uint32_t t : {500u, 999u, 1500u, 2999u}) {
        assert(equal(error.color(t), Color{0, 0, 0}));
    }

    // Every animation respects the brightness ceiling, including fully off.
    for (unsigned state = 0; state < static_cast<unsigned>(State::Offline); ++state) {
        for (unsigned brightness = 0; brightness <= 128; ++brightness) {
            Light sample;
            assert(sample.set(static_cast<State>(state), static_cast<uint8_t>(brightness), 0));
            for (uint32_t t = 0; t <= 10000; t += 37) {
                sample.advance(t);
                const Color color = sample.color(t);
                assert(color.red <= brightness && color.green <= brightness && color.blue <= brightness);
            }
            sample.advance(15000);
            for (uint32_t t = 15000; t <= 25000; t += 37) {
                const Color color = sample.color(t);
                assert(color.red == color.green && color.green == color.blue && color.red <= brightness);
            }
        }
    }
}

} // namespace

int main() {
    parserTests();
    heartbeatTests();
    animationTests();
    puts("firmware parser, watchdog and animation tests passed");
}
