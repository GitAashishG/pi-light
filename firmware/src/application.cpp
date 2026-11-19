#include "Particle.h"
#include "deviceid_hal.h"
#include "light_core.h"
#include "rgbled.h"

#include <stdio.h>
#include <string.h>

#if PLATFORM_ID != 6
#error "pi-light firmware targets the original Photon (platform 6), not Photon 2 or other boards"
#endif

SYSTEM_MODE(MANUAL);
SYSTEM_THREAD(ENABLED);
STARTUP(WiFi.off());

namespace {

pilight::Light light;
pilight::LineParser parser;
char deviceId[25] = {};
bool wasConnected = false;
pilight::Color requested = {255, 255, 255};

// A slow/unread USB peer cannot stall animations or the offline watchdog.
class OutputQueue {
public:
    size_t available() const { return sizeof(bytes_) - size_; }
    void clear() { head_ = 0; size_ = 0; }
    void append(const char* text) {
        const size_t length = strlen(text);
        if (length > available()) {
            return; // Callers reserve a complete maximum-sized reply before reading.
        }
        for (size_t i = 0; i < length; ++i) {
            bytes_[(head_ + size_) % sizeof(bytes_)] = text[i];
            ++size_;
        }
    }
    void drain() {
        for (size_t sent = 0; sent < 64 && size_ != 0 && Serial.availableForWrite() > 0; ++sent) {
            if (Serial.write(static_cast<uint8_t>(bytes_[head_])) != 1) {
                break;
            }
            head_ = (head_ + 1) % sizeof(bytes_);
            --size_;
        }
    }

private:
    char bytes_[384] = {};
    size_t head_ = 0;
    size_t size_ = 0;
};

OutputQueue output;

void applyColor(uint32_t now) {
    light.advance(now);
    const pilight::Color color = light.color(now);
    if (color.red != requested.red || color.green != requested.green || color.blue != requested.blue) {
        RGB.color(color.red, color.green, color.blue);
        requested = color;
    }
}

void hello() {
    char reply[48];
    snprintf(reply, sizeof(reply), "PI-LIGHT 1 %s\n", deviceId);
    output.append(reply);
}

void acknowledge(uint32_t sequence, uint32_t now) {
    applyColor(now);
    // Device OS reads the applied PWM compare registers and normalizes to 0..255.
    // This captures Device OS brightness/quantization, not merely requested RGB.
    uint8_t applied[3] = {};
    LED_RGB_Get(applied);
    char reply[pilight::kMaxLineBytes];
    snprintf(reply, sizeof(reply), "PI1 %lu %s %u %u %u\n",
             static_cast<unsigned long>(sequence), pilight::stateName(light.state()),
             static_cast<unsigned>(applied[0]), static_cast<unsigned>(applied[1]),
             static_cast<unsigned>(applied[2]));
    output.append(reply);
}

void handle(const pilight::Command& command, uint32_t now) {
    switch (command.kind) {
        case pilight::CommandKind::Hello:
            hello();
            break;
        case pilight::CommandKind::Query:
            acknowledge(command.sequence, now);
            break;
        case pilight::CommandKind::Set:
            light.set(command.state, command.brightness, now);
            acknowledge(command.sequence, now);
            break;
        case pilight::CommandKind::Invalid:
            output.append("ERR invalid-command\n");
            break;
    }
}

} // namespace

void setup() {
    // Manual mode never starts Wi-Fi or Particle cloud. No credentials are read,
    // changed, or erased. Do not enable automatic connection or listening mode.
    RGB.control(true);
    RGB.brightness(255, false); // Per-command brightness is applied by the core.
    applyColor(millis());

    uint8_t identity[12] = {};
    HAL_device_ID(identity, sizeof(identity));
    constexpr char hex[] = "0123456789abcdef";
    for (size_t i = 0; i < sizeof(identity); ++i) {
        deviceId[i * 2] = hex[identity[i] >> 4];
        deviceId[i * 2 + 1] = hex[identity[i] & 15];
    }
    deviceId[24] = '\0';
    Serial.begin(115200);
    Serial.blockOnOverrun(false);
}

void loop() {
    applyColor(millis());
    const bool connected = Serial.isConnected();
    if (connected != wasConnected) {
        parser.reset();
        output.clear();
        wasConnected = connected;
        if (connected) {
            hello();
        }
    }
    if (!connected) {
        return;
    }
    output.drain();
    for (size_t received = 0; received < 64 && output.available() >= pilight::kMaxLineBytes; ++received) {
        const int byte = Serial.read();
        if (byte < 0) {
            break;
        }
        pilight::Command command;
        if (parser.feed(static_cast<uint8_t>(byte), command)) {
            handle(command, millis());
        }
    }
    output.drain();
}
