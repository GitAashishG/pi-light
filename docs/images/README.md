# Documentation images

These images come from contributor-supplied footage of the actual pi-light prototype. They are documentation stills, not generated product renders or screenshots of inferred agent activity. Raw recordings are not included in the repository.

| Image | Source | Purpose |
|---|---|---|
| `pi-light.jpg` | `IMG_5135.MOV`, frame near 22 seconds | Finished purple enclosure, illuminated RGB window, and USB connection. |
| `assembly.jpg` | `IMG_5134.MOV`, frame near 5 seconds | Original Photon orientation inside the prototype tray and the USB connector location. |

The interior photo is an orientation reference, not an instruction to assemble a powered board. Disconnect USB before fitting or removing the board. The pictured prototype uses a removable lid and temporary tape; it does not demonstrate a universal fit or a validated snap lock.

## Processing

- Applied each source's stored portrait transform.
- Converted the 10-bit HLG/BT.2020 sources to SDR using AVFoundation's `forceSDR`, then encoded sRGB JPEGs. No creative color shift was applied.
- Cropped out the monitor and unrelated background. The enclosure still uses the real filmed LED color; clipped highlights are not reconstructed.
- Covered the shield's QR and adjacent identifying text in the interior photo with an opaque polygon. The redaction is deliberate; the public image cannot recover the original pixels.
- Wrote new JPEGs from decoded pixels, without copying source EXIF, GPS, capture date, author, camera/device or location metadata. JPEG color/profile and dimension information may remain.

For reproducibility, crop rectangles below use top-left coordinates in the upright 2160 × 3840 source frame:

| Output | Actual source time | Crop `(x, y, width, height)` | Output size |
|---|---:|---|---|
| `pi-light.jpg` | 21.988333 s | `(0, 1900, 2160, 1500)` | 1200 × 834 |
| `assembly.jpg` | 4.988333 s | `(250, 1300, 1910, 1650)` | 1200 × 1037 |

The interior privacy polygon uses top-left coordinates in the resized image: `(545,197)`, `(636,246)`, `(557,381)`, `(465,330)`. Original media and unredacted working frames remain outside the publishable source tree.
