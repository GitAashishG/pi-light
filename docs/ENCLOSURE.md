# Desk enclosure

Use a nonconductive tray with a removable lid for the **original Particle Photon**, its onboard RGB LED and a data-capable Micro-USB cable. Photon 2 and Spark Core have different geometry. The case described here is a first-fit design; check your board, soldered headers and cable before printing the full parts.

## Printable parts

Download the two fit pieces first, then the full tray and lid after checking the fit. All four STL files use millimeters and include their intended printing orientation.

| Part | Download |
|---|---|
| 12 mm USB-end tray section | [fit_base.stl](print/fit_base.stl) |
| Matching USB-end lid section | [fit_lid.stl](print/fit_lid.stl) |
| Full tray | [base.stl](print/base.stl) |
| Full lid | [lid.stl](print/lid.stl) |

## Materials and geometry

Use ordinary nonconductive PLA for the tray and lid, a small piece of parchment or tracing paper for diffusion, and removable tape. Do not use conductive filament, metal fasteners near the pins, or loose conductive hardware inside the case. No extra LED, printed translucent insert or mounting screws are required.

All dimensions below are in millimeters. The PCB outline and LED/button locations come from Particle's [original Photon board file](https://github.com/particle-iot/photon/blob/master/eagle/photon_v100/photon_v1.0.0.brd). The remaining values are enclosure design allowances, not measurements of your hardware.

| Feature | Dimension or allowance |
|---|---:|
| PCB width × length | 20.32 × 36.576 |
| Case width × length × assembled height | 25.12 × 41.376 × 19.2 |
| Tray wall / floor / lid plate thickness | 2 / 1.6 / 1.6 |
| Tray height, excluding lid plate | 17.6 |
| Clearance around PCB | 0.4 per side |
| PCB underside height above exterior bottom | 10 |
| Assumed PCB thickness | 1 |
| Space below PCB underside, above floor | 8.4 |
| Modeled header projection below PCB | 8, leaving 0.4 above the floor |
| Lid registration skirt thickness / depth | 0.8 / 2 |
| Clearance between skirt and tray | 0.2 per side |
| Gap above PCB at the two lid hold-downs | 0.4 |
| RGB aperture | 6 diameter |
| Diffuser recess on lid interior | 14 diameter × 0.4 deep |
| USB opening width | 14 |
| USB opening bottom above exterior bottom | 7.6 |
| USB opening height with lid fitted | 11.6, comprising a 10-high tray notch and the 1.6-thick lid edge cutout |
| USB-end fit pieces | 12 long |

Orient the board with its Micro-USB connector toward the open end of the tray. In a top view with the antenna end at y=0, the RGB LED center is x=10.16, y=25.4 on the PCB, or 11.176 from the USB-side PCB edge. With the PCB centered in this case, the aperture center is x=12.56, y=27.8 from the case's antenna-side corner.

The board rests on four supports under the short ends of the PCB, away from the header rows and underside test pads. The board has no mounting holes. The lid's two hold-downs leave a gap above component-free PCB areas; they must not press the antenna, shield, buttons or USB connector. Keep the lid removable for service.

## Print orientation and fit pieces

1. Measure the actual pin projection, board thickness and cable overmold. Compare them with the allowances above. Increase the case clearance in CAD if the pins would touch the floor or the plug cannot reach the socket.
2. Print the two 12 mm USB-end sections before the full tray and lid. These sections check local board seating, cable insertion and skirt fit. They do not check the antenna end, full-length lid friction or LED diffusion.
3. Print the tray floor-down. Print the lid with its exterior face against the bed and its skirt and hold-downs pointing upward. The STL downloads already use these orientations. The paper recess must face upward during printing.
4. Use a printer/material profile appropriate to your machine. Start with a 0.4 mm nozzle and 0.20 mm PLA layers. Inspect the slice for unsupported regions and first-layer expansion before printing; support-free geometry and a clean slice do not establish physical fit. Keep the model at 100% scale and adjust the CAD clearances rather than scaling every feature.
5. Test the fit pieces with power disconnected. Support the rest of the board while checking the short tray section. The PCB should rest flat without pins bottoming out, and the lid should seat and lift off without bending the board or forcing the skirt.

The lid uses a registration/push fit, not a snap catch. If the fit is tight, adjust the skirt clearance and reprint the small pair. If it is loose, reduce the clearance or use removable seam tape after assembly. Do not rely on the lid to stay closed upside down, and do not glue it shut.

## Diffuser and final assembly

1. Print the full tray and lid after the USB-end fit check. Remove loose plastic and inspect the supports and openings before inserting the board. Disconnect USB while fitting the hardware.
2. Place the board on all four supports. Confirm that header tips clear the floor, solder joints do not catch on the supports, and no printed feature pushes on components. Stop if seating the board requires force.
3. Cut a paper disc slightly smaller than the 14 mm recess. Tape it to the **inside of the lid, behind the 6 mm aperture**. Keep the tape and paper clear of the LED, buttons and PCB. The recess leaves 1.2 mm of lid material around the through-hole; there is no printed optical insert.
4. Fit the lid with the aperture above the RGB LED and the lid's USB cutout aligned with the tray opening. Check that the skirt and hold-downs clear the board. Remove the lid again if closing it changes the board's position.
5. Insert the actual Micro-USB plug through the opening. It must seat fully without its overmold stopping against the wall, lifting the board or loading the connector sideways. Confirm that you can grip and remove the plug without levering the socket.
6. Route the cable with slack and a gentle bend outside the case. The opening provides clearance, not a cable clamp. Add external strain relief if cable movement would pull on the board.
7. Reconnect USB and check the LED from the normal desk viewing position. Confirm that colors and pulse patterns remain distinguishable through the diffuser. Adjust the paper if the bare LED is glaring or the signal is too dim. Paper diffusion is not a seal or a heat-management system.

## USB and recovery access

USB carries both power and data. A case that allows charging but prevents full connector insertion can still break the serial connection, so confirm that the host detects the board after assembly. In normal pi-light operation the board does not join Wi-Fi or the Particle cloud; loss of the bridge eventually produces a dim-white offline pattern.

Remove the lid to reach SETUP and RESET. To enter DFU manually, hold SETUP, tap RESET, and keep holding SETUP until the LED blinks yellow. Make sure the diffuser can be lifted out of the way if it obscures the recovery LED. Use the device-identification and recovery steps in [Build and flash the Photon](FIRMWARE.md) before writing firmware; access to the buttons alone does not identify the connected board.

Before using the case on a desk, confirm full USB insertion and removal, accessible SETUP/RESET buttons, a removable lid, clearance beneath the header pins, and readable status colors. CAD collision checks cannot replace these physical checks.
