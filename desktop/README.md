# Open Motion: G-LOC desktop prototype

Windows 10 x64 first. Controller protocol: **115200 baud, 8 data bits, no parity,
1 stop bit**, using the existing `Q/R/S/T/A/B` commands terminated with `x`.
Prepared for Luke McMillan's Core i7-1065G7 test machine.

This is a development build, not a cabinet-validated release. The launcher,
serial bridge and update installer have automated tests. Windows executable
compilation and the complete game-to-controller path are checked separately.
A passing build does not establish real cabinet polarity, calibration or travel.

## Get the Windows test package

The GitHub Actions workflow **Open Motion desktop test build** produces:

1. **Application**: portable `OpenMotion.exe` and its `_internal` folder. Keep both.
2. **Emulator update ZIP**: matched custom MAME 0.276 with the desktop drivers.
3. **ROM patch update ZIP**: frozen recipes, separate from the emulator.
4. **Corresponding MAME source**: the complete patched source for that executable.

Extract the application somewhere writable and run `OpenMotion.exe`. Choose
**Setup → Install update ZIP** for the emulator package, then the ROM-patch
package. Import a complete personal ROM ZIP under its selected game. The
application saves a separate original and installs a patched copy. No Sega game
or device ROM is included in GitHub or the executable distribution.

Start with **Play**, which always opens in **monitor-only** mode. It does not open
the serial port. Set the controller port in Setup when ready for a bench check.
The old COM7 value is not assumed. Baud is fixed to the confirmed 115200.

## Controls and display

The launcher has a 320×240 minimum window with a large, short game list, and
scales up for desktop use. Arrow keys move, Enter selects, Escape goes back.
F2 opens setup, Ctrl+I imports a game and F6 opens the host monitor. On Windows,
focused launcher navigation can also use either A-PAC gamepad's Y axis and first
two buttons. These are initial navigation defaults, not an imported A-PAC map.
MAME receives both gamepads directly with `-joystick`; it owns in-game bindings.
Use **Tab → Input Settings** in MAME to bind the yoke, throttle and buttons.

In-game **F6** cycles compact overlay, detailed overlay and off. Compact shows
Q/R targets, speeds and bridge mode. Detailed adds the latest serial write and
controller text received. TX means bytes accepted by the serial driver; it does
not mean the cabinet reached that position. RX is raw firmware text, not a
validated encoder/status packet. The current overlay uses MAME's UI font size;
font-size presets and testing on an actual 320×224/240 cabinet monitor remain.

The first version does not yet provide the complete A-PAC binding wizard,
remappable overlay shortcut in the UI, motor-jog/calibration tools or Pi image.

## Games and frozen translations

| Game | ROM patch | Desktop implementation |
|---|---|---|
| G-LOC | Original | Existing Y-board MAME outputs; original INI mapping |
| Strike Fighter | Original | Existing Y-board MAME outputs; original INI mapping |
| Galaxy Force II | 1.2 | `gforce2gloc` clone and converted-ROM output decoder |
| Wing War R360 | 0.3 | Desktop publication of the existing ROM byte stream |
| After Burner II | 0.2 | Existing custom X-board feedback and mailbox driver |
| Space Harrier / older revision | 0.1 | Custom Hang-On driver, explicit MCU HLE |

The ROM patch payloads are unchanged. The Galaxy Force II recipe is normalised
to the launcher's common recipe format, with identical output chip checksums.
Its desktop clone hashes match the frozen v1.2 chips. The ROM decoder must be
enabled under Machine Configuration; the integration enables it for this clone.
Wing War's desktop path recognises its patched I/O payload before interpreting
its bytes as G-LOC commands. The original R360 status/throttle handling remains.

Original G-LOC and Strike Fighter follow `gloc.ini` / `strkfgtr.ini` exactly for
normalised positions. The conversions use the Lab's cabinet-space inversion
(`32 - raw position`). This difference is explicit and needs a real bench check.
There is no automatic extra axis inversion or live gain adjustment.

The stored driver snapshots used browser-only callbacks in places. This package
adds normal MAME outputs for Wing War and uses an ordered, local-only output
transport in place of 0.276's shared asynchronous buffer. It does not transplant
current MAME's newer output module API into the old source tree.

## Motion connection and loss

Enabling motion is a deliberate per-session action from Command Monitor. A live
MAME session token, valid complete pose and advancing frame stream are required.
The bridge sends `MODESx` because the v55 repository source defaults to parallel,
then a centre packet, then complete pose/lamp packets at up to 20 Hz. It drains
controller replies to prevent its debug text filling the receive buffer.

Opening a Mega USB port can reset some adapters and start firmware calibration.
The user must establish that the controller is calibrated and ready before
motion is enabled. There is no firmware-ready acknowledgement in this version.
Source selection has no acknowledged response either; the app reports writes,
not a proven mode change. The firmware sketch itself is not changed here.

Pause, output loss over 500 ms, invalid packets, process exit, session mismatch
or serial failure disable motion. Where the connection is working, the bridge
requests centre and closes the port. Resume never rearms automatically. The
firmware's existing timeout is the fallback when the PC cannot send anything.
**Centre is movement, not an emergency stop.** Use the cabinet's physical stop.
The v55 PID implementation does not currently use its received speed scalars to
scale normal PID drive; sending varying S/T values does not prove varying real
motor speed. Firmware changes are a separate workstream.

## Updates and settings

Cabinet settings, original ROMs, MAME bindings, NVRAM and per-session logs live
under `%APPDATA%\OpenMotion\GLOC`, outside application and emulator packages.
`OPEN_MOTION_HOME` can select another user-data folder for development.

Offline update ZIPs contain `manifest.json` and a hash-checked `payload/` tree.
Emulator and patch packages have separate versions and compatibility IDs. The
installer stages each version in its own directory, refuses replacement of an
existing version, and never replaces cabinet settings. Setup → Emulator package
can select an earlier installed executable. Patch updates can be installed
separately and require re-importing an original ROM to apply their recipe.
Automatic online discovery, signed-release verification, user-facing patch
version selection and a full test/promote/rollback flow remain future work.
Use update packages from the project author; hashes detect corruption, not trust.

## Development

Python 3.11 with Tk, plus `pip install -r requirements.txt`:

```
python -m unittest discover -s tests -v
python app.py
```

`build/prepare_mame.py` verifies every changed upstream file's SHA256 before
applying the tracked patches to pristine MAME 0.276. Upstream archive:
`https://codeload.github.com/mamedev/mame/tar.gz/refs/tags/mame0276`
SHA256: `965dfc33d720b4c3c6e425d5959540bd0bac88e96b878a8560678c2f5b43c44f`.

```
python desktop/build/prepare_mame.py /path/to/mame0276
cd /path/to/mame0276
make SUBTARGET=openmotion SOURCES=src/mame/sega/segaybd.cpp,src/mame/sega/segaxbd.cpp,src/mame/sega/segahang.cpp,src/mame/sega/model1.cpp REGENIE=1 SYMBOLS=0 OPTIMIZE=2 -j2
```

The application is separate from MAME. MAME and the driver modifications retain
their upstream GPL/BSD licensing; see `patches/LICENSE.md`. Root project licence
applies to the launcher, bridge and project assets, not the combined MAME build.

Authorship: **Luke McMillan**.
Project: https://github.com/BertyB3/OpenMotionGLOC
