# Desk enclosure

The owner is printing the enclosure. The project needs only the original Photon, its onboard RGB LED and a data-capable USB cable; no LED strip, mains relay or extra sensor is required.

Use a translucent diffuser above the RGB LED so the small onboard light remains visible from the desk. Test a thin white/translucent material sample before printing the full shell; pigment and wall thickness affect color and brightness. Give the LED a clear path to the diffuser rather than burying it behind an opaque roof.

Measure the actual board, header pins, Micro-USB plug and cable bend radius. Leave clearance beneath the PCB, use nonconductive standoffs, and avoid screws or conductive filament touching pins. Provide cable strain relief and enough room to unplug the connector without levering the board.

Keep RESET and SETUP reachable through service holes or a removable lid so DFU recovery remains possible. A printed state legend helps distinguish colors; the firmware also uses different pulse patterns. Avoid placing a bright bare LED at eye level. Brightness is software-limited and defaults to a restrained level for indoor use.

USB carries both power and data to this Mac. The board does not join Wi-Fi or the Particle cloud. If the bridge disappears, the device times out to a dim-white offline pattern instead of keeping a misleading green success light.
