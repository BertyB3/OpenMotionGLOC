# Local verification: 13 November 2026

- 15 unit tests passed, including all 7,168 valid Q/R/speed combinations with
  both heartbeat polarities, serial mode selection/order, pause and timeout
  disarming, corrupt packets, session mismatches, write failures, ZIP path
  validation, hashes and settings preservation.
- All five frozen conversion recipes reproduce the shipped ROM members
  byte for byte after reversing to verified original program CRCs. This covers
  both Space Harrier revisions. The ROMs are private local test inputs and are
  not included in this repository.
- The actual MAME 0.276 Linux executable loaded the Lua plugin, exercised its
  frame and rendering callbacks and sent a synthetic output fixture over TCP
  to the actual Python bridge. Session, pose and monitor-only behaviour passed;
  no serial device was opened. This does not verify native game cues or visual
  layout: the smoke run uses `-video none` and an explicit synthetic pose.
- `network.cpp`, `segaxbd.cpp`, `segahang.cpp`, `segaybd.cpp` and `model1.cpp`
  passed GCC 14 C++17 syntax checks against complete official 0.276 headers and
  generated layout headers. This is not a complete executable link.
- Every upstream file preimage was SHA256-verified and all five patches applied
  successfully to the official source archive with the pinned SHA256.

Pending: Windows compilation, full linked custom-MAME runtime, visible UI/overlay
inspection, actual A-PAC navigation, serial hardware, physical cabinet polarity,
limits and calibration, performance on the i7-1065G7, and Raspberry Pi support.
GitHub publication/build execution was blocked by automatic approval review;
no Windows executable or completed GitHub Actions run is claimed here.
