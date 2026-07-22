# Smart Priority Bopomofo native candidate UI

This directory contains the source and reproducible build script for the
Japanese-inspired candidate window bundled with Smart Priority Bopomofo.

- Upstream PIME commit: `26fcf6ac8874e76b8f75f6826811b03bfdfc2e89`
  (`v1.3.0-stable`, matching the bundled PIME runtime)
- Upstream libIME2 commit: `8ad3c9b433d930ce5614c483461dfa78cedb5efd`
- Upstream: https://github.com/EasyIME/PIME
- License: LGPL-2.0-or-later; see `LGPL-2.0.txt`.

`src/CandidateWindow.cpp` is the complete modified source. The UI uses a warm
paper background, indigo accents, rounded clipping, a thin neutral border,
DPI-scaled spacing, and double-buffered painting. `src/CMakeLists.txt` excludes
PIMELauncher because the product keeps the signed launcher's existing binary
and rebuilds only `PIMETextService.dll`.

Run `build_native_ui.ps1` on Windows with Visual Studio 2022 C++ tools to
reproduce `bin/x86/PIMETextService.dll` and `bin/x64/PIMETextService.dll`.

These locally built DLLs are not code-signed and are therefore not installed
by default. The source installer accepts the explicit
`-EnableUnsignedNativeUi` switch when no other PIME input-method modules are
present. It backs up the original shared DLLs and remembers the opt-in across
normal and EXE updates. `-DisableUnsignedNativeUi` or uninstall explicitly
restores the signed PIME binaries when game or anti-cheat compatibility is
more important than the custom appearance.
