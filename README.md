# ECEN 5833 xG24 starter

A bare-metal starter with a periodic workload, managed sleep, a kit demo, and saved energy captures. Hosts: Windows x64, macOS Intel/Apple Silicon, and Linux x64. Simplicity Studio is not required.

## Set up

Install [Git](https://git-scm.com/downloads/), [VS Code](https://code.visualstudio.com/), and [SEGGER J-Link Software](https://www.segger.com/downloads/jlink/).

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) in **Windows PowerShell**:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
```

Or in a **macOS/Linux terminal**:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
```

Download **SLT 1.2.1** for your computer:

| Windows x64 | macOS Intel | macOS Apple Silicon | Linux x64 |
|---|---|---|---|
| [Download](https://www.silabs.com/documents/public/software/slt-cli-1.2.1-windows-x64.zip) | [Download](https://www.silabs.com/documents/public/software/slt-cli-1.2.1-mac-x64.zip) | [Download](https://www.silabs.com/documents/public/software/slt-cli-1.2.1-mac-arm64.zip) | [Download](https://www.silabs.com/documents/public/software/slt-cli-1.2.1-linux-x64.zip) |

Extract the archive. Copy `slt.exe` to `%USERPROFILE%\.local\bin` on Windows, or `slt` to `~/.local/bin` on macOS/Linux. This is the same directory added to PATH above. On macOS/Linux, run `chmod +x "$HOME/.local/bin/slt"`.

On Ubuntu/Debian, run `sudo apt-get install libusb-1.0-0 gdb-multiarch`. On Linux, install J-Link's USB rules as described in its package README, then reconnect the kit.

Fully close and reopen VS Code or your terminal. Confirm that all three commands print a version:

```text
git --version
uv --version
slt --version
```

Create your team's repository by opening [this starter](https://github.com/cchoi22915/ECEN5833-xg24-starter) and selecting **Fork**. In VS Code, open the Command Palette (**Ctrl/Cmd+Shift+P**), choose **Git: Clone**, paste your fork's HTTPS URL, and open the cloned folder.

Install the recommended **C/C++**, **CMake Tools**, and **Cortex-Debug** extensions. Choose **Terminal → Run Task → Starter: first setup**. It runs Python sync, locked tool installation, debugger checks, and the demo build in order. The first setup requires an internet connection.

Success: doctor prints **Debugger tools found** and the build ends with **Built** followed by `build/demo/base/series2_starter.out` (Windows uses backslashes).

Open `.local/starter.code-workspace` using **File → Open Workspace from File**. This supplies the full tool paths for F5; IntelliSense follows the latest successful build.

First setup installs Python 3.14.8, SDK 2026.6.1, GCC 14.2.1, and the locked dependencies. Keep `pkg.lock` and `uv.lock`. After starter updates, rerun **Starter: first setup**. [Command-line setup](#command-line-setup) is also available.

## Run on the Pro Kit

Default target: **BRD4186C / EFR32MG24B210F1536IM48**. Read the radio board's BRD label for MCU selection; USB-C identifies the mainboard. Match your board and debugger device before programming; see [Change board or module](#change-board-or-module).

1. Connect a USB data cable to the Pro Kit's **J-Link USB-C** port. Set power to **AEM** and debug mode to **MCU**.
2. In **Run and Debug**, select **Starter: debug demo (BRD4186C)** and press **F5**. It builds, programs, and stops at `main`.
3. Click **Continue**. The LCD should show **ECEN 5833**, **CU BOULDER**, and the CU logo. LED0 should brighten and dim over a four-second cycle.

## Make your first edit

In `firmware/include/app_config.h`, change `APP_LED_BREATH_STEP_MS` from `20u` to `40u`. Press F5 and **Continue**. LED0 should now take about eight seconds to brighten and dim. Use a new capture filename when comparing changes.

## Capture energy

Stop debugging, press the kit's **RESET** button, and leave power set to **AEM**.

1. Choose **Terminal → Run Task → Starter: capture energy**. Enter a new CSV filename, such as `captures/demo.csv`, and the duration in seconds (default: `10`). Existing captures are refused.
2. Choose **Starter: plot capture** and enter the saved CSV filename. It writes a PNG beside the CSV, such as `captures/demo.png`.
3. Open the PNG in VS Code. The demo's PWM period is 10 ms; its on-time changes with LED brightness.

CSV units are timestamp **µs**, current **mA**, and voltage **V**. For continuous captures, capture and plot print average current/power and integrated charge/energy. Files with sample gaps show a warning and broken traces; full-capture totals are withheld. Captures stay local and are ignored by Git; plotting works without a kit.

If sleep current stays high after debugging, stop the session and reflash with Commander before capturing. [Power modes and capture options](#power-modes-and-capture-options) covers comparisons, short pulse captures, logging rate, and kit selection.

## Start your project

Edit `firmware/`. Builds regenerate the SDK output when your inputs change.

| File | Put your changes here |
|---|---|
| `firmware/src/app.c` | Initialize drivers in `app_init()`; process events and project work in `app_process_action()` |
| `firmware/src/workload.c` | Replace the synthetic work and its call in `app.c` with your application logic |
| `firmware/include/app_config.h` | Work interval, queue limit, and demo breathing interval |
| `firmware/series2_starter.slcp` | Board, SDK components, source files, headers, and component settings |

Add new `.c` files under `firmware/src/` and register them under `source` in the `.slcp`. Add headers under `firmware/include/` and register them in `include` → `file_list`. Keep interrupt/timer callbacks short: post events, then process them in the main loop. Add tests when you change application behavior.

Bluetooth, sensors, and custom PCBs need their own stack/driver/board integration. The synthetic workload is a starting point for your project logic.

## Troubleshooting

| Symptom | Check |
|---|---|
| `uv` or `slt` is not recognized | Confirm the executable is in `.local/bin`; repeat your OS's PATH command above. Fully restart VS Code for future terminals. |
| F5 cannot find `uv`, GDB, or J-Link | Open `.local/starter.code-workspace`, install the recommended extensions, and rerun `doctor --debug`. Windows tasks expect the uv installer location shown above. |
| Kit is not detected | Use the J-Link USB port and a data cable; close other debugger/Commander connections. Check J-Link drivers or Linux USB rules. |
| LCD is blank / LED is off | Continue past `main`; confirm you flashed `demo` for the correct board and selected AEM/MCU. The comparison modes disable the demo. |
| SDK headers show errors in the editor | Build the desired mode successfully, then reload VS Code. IntelliSense uses `.local/compile_commands.json`. |
| Setup or build fails | Check the first error in `.local/logs/`; rerun **Starter: first setup** after starter toolchain updates. |

## Optional

### Command-line setup

Run from the repository root:

```text
uv sync --locked
uv run --locked python tools/firmware.py setup
uv run --locked python tools/firmware.py doctor --debug
uv run --locked python tools/firmware.py build
```

### Flash without debugging

To flash without a debug session, open Commander:

```text
uv run --locked python tools/firmware.py commander
```

In Commander, select the connected kit, open **Flash**, select `build/demo/base/series2_starter.hex`, and flash it. Press the kit's **RESET** button to run.

### Power modes and capture options

| Build mode | Idle behavior | LCD / LED PWM |
|---|---|---|
| `demo` (default) | EM1; 100 Hz PWM, duty sweeps 0–100–0% | On |
| `awake` | CPU stays awake | Off |
| `em1` | EM1 | Off |
| `em2` | EM2 permitted; active requirements determine the actual mode | Off |

All modes retain the same one-second workload interval. Select a mode with `build --mode MODE` and the matching F5 configuration.

For power optimization, build with `--mode em2` and select **Starter: debug em2**. This disables the demo display/PWM and breathing timer and removes the demo's EM1 requirement. Preserve any energy-mode requirements needed by your own drivers. When removing demo source/components entirely, update the demo calls and timer/EM1 logic in `app.c` together.

The same capture/plot operations are available from the terminal:

```text
uv run --locked python tools/energy_profile.py capture captures/demo.csv --seconds 10
uv run --locked python tools/energy_profile.py plot captures/demo.csv
```

For a clear view of individual PWM pulses, capture with `--seconds 0.1` to a new file such as `captures/pwm-detail.csv`, then plot that file.

Build/flash each comparison mode with `build --mode awake`, `em1`, or `em2` and use its HEX from `build/<mode>/base/`. Capture each to a separate CSV, then compare:

```text
uv run --locked python tools/energy_profile.py plot captures/awake.csv captures/em1.csv captures/em2.csv --output captures/comparison.png
```

Default logging rate is 10,000 Hz; change it with `--rate`. Lower rates average samples and can hide short peaks. Use `--serial SERIAL` when multiple kits are connected.

Capture checks timestamps against the requested logging rate. Offline plotting infers the typical interval; add `plot --rate RATE` using the original logging rate to detect uniformly spaced missing samples too. Intervals longer than 1.5 times the expected interval are flagged. Gapped files still plot for diagnosis, but require a new continuous capture before quantitative comparisons.

Compare modes at the same supply voltage, workload, duration, and logging rate. AEM measures the target supply load; account for LEDs, displays, and sensors powered from that supply. Record the board, firmware mode/revision, voltage, and capture settings with your measurements.

### Change board or module

Disconnect kit power before swapping a radio board. In `firmware/series2_starter.slcp`, replace `- id: brd4186c` with the component for your **actual board and revision**. Keep `brd4002a` if using the same USB-C mainboard.

| Radio board | Component ID | SDK target |
|---|---|---|
| xG24 BRD4186C | `brd4186c` | EFR32MG24B210F1536IM48 |
| xG26 BRD4117A | `brd4117a` | EFR32MG26B420F3200IM48 |
| MGM260P BRD4350A rev A05 | `brd4350a_a05` | MGM260PD22VNA |
| MGM260P BRD4351A rev A05 | `brd4351a_a05` | MGM260PD32VNA |

Board support selects the device, clocks, LCD and LED pins. For another Silicon Labs board, use its SDK component ID and verify the selected part against its kit guide. An MGM module and an EFR32 SoC radio board use different components. Custom PCBs need their own pin/clock configuration; boards without the kit LCD/LED need the demo adapted.

Update `device` in **every** `.vscode/launch.json` configuration to the exact MCU part from Commander Device Info or the kit guide, and update the board labels. Modules may report their underlying EFR32 MCU. Regenerate and rebuild:

```text
uv run --locked python tools/firmware.py generate
uv run --locked python tools/firmware.py build
```

Confirm the selected part in `generated/cmake_gcc/series2_starter.cmake` before flashing. xG26/module examples need matching hardware; a successful build alone does not verify the board.

### Tests

Run the Python tool tests:

```text
uv run --locked python -m unittest discover -s tests -p "test_*.py" -v
```

The supplied CI workflow also runs C event/failure tests. With a native host C compiler and CMake installed, run those locally with:

```text
cmake -S tests -B build/host -DCMAKE_BUILD_TYPE=Debug
cmake --build build/host --config Debug
ctest --test-dir build/host -C Debug --output-on-failure
```

### Energy model

To calculate a state-duration energy model:

```text
uv run --locked python tools/energy_budget.py examples/illustrative_energy_model.json
```

Replace the example's `current_a`, `duration_s`, and `voltage_v` with measured/project values. Convert CSV mA to A by dividing by 1,000; durations are in seconds. Its supplied values are illustrative. The result is average current and energy per period, not a battery-life estimate.
