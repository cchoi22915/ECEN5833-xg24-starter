#!/usr/bin/env python3
"""Set up, generate and build with standalone SLT/SLC on Windows, macOS and Linux."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tomllib

# Shared defaults live here. Keep SDK/GCC versions consistent with pkg.slt and pkg.lock.
ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"
GENERATED = ROOT / "generated"
PROJECT = GENERATED / "cmake_gcc"
# These numeric values must match firmware/include/app_config.h.
MODES = {"awake": 0, "em1": 1, "em2": 2, "demo": 3}
SDK_VERSION = "2026.6.1"
GCC_VERSION = "14.2.1"
DEFAULT_MODE = "demo"
BUILD_JOBS = 4
LINUX_GDB = "gdb-multiarch"
UV_BIN_DIRECTORY = ".local/bin"
INTELLISENSE_DATABASE = "compile_commands.json"
# Verify code and headers, excluding Finder metadata and editor backup files.
SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx", ".s", ".asm", ".inc"}
JLINK_BASES = {"darwin": (Path("/Applications/SEGGER"), Path.home() / "Applications/SEGGER"),
               "linux": (Path("/opt/SEGGER"),)}
JLINK_NAMES = {"win32": ("JLinkGDBServerCL.exe",),
               "darwin": ("JLinkGDBServerCLExe", "JLinkGDBServer"),
               "linux": ("JLinkGDBServerCLExe", "JLinkGDBServer")}


def executable(name):
    # Vendor tool names differ only by the executable suffix on Windows.
    return name + (".exe" if sys.platform == "win32" else "")


def uv_path():
    # A freshly installed uv may be present before the editor's PATH is refreshed.
    found = shutil.which(executable("uv"))
    candidate = Path(found) if found else Path.home() / UV_BIN_DIRECTORY / executable("uv")
    if not candidate.is_file():
        raise RuntimeError("Install uv and rerun setup. See README.md.")
    return candidate.resolve()


def digest(path):
    # Record exact file contents so setup/build records can detect stale inputs.
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local_path(path):
    # Resolve symlinks as well as '..' before accepting a generated output path.
    resolved = path.resolve()
    if resolved == ROOT or ROOT not in resolved.parents:
        raise RuntimeError(f"Output must stay inside this repository: {resolved}")
    return path


def run(label, command, cwd=ROOT, env=None):
    # Pass arguments separately: spaces and shell characters remain literal.
    print(f"{label} ...", flush=True)
    result = subprocess.run([str(arg) for arg in command], cwd=cwd, env=env,
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    output = result.stdout + result.stderr
    # Save command output locally so a failed setup/build can be diagnosed later.
    log = local_path(LOCAL / "logs" / (label.lower().replace(" ", "-") + ".txt"))
    log.parent.mkdir(parents=True, exist_ok=True)
    quote = subprocess.list2cmdline if sys.platform == "win32" else shlex.join
    log.write_text(quote([str(arg) for arg in command]) + "\n\n" + output, encoding="utf-8")
    if output:
        print(output.rstrip(), flush=True)
    if result.returncode:
        raise RuntimeError(f"{label} failed (exit {result.returncode}). See {log}")
    return output.strip()


def slt_path():
    # Support both the standalone CLI and the installer's bundled CLI.
    candidates = [shutil.which(executable("slt")), Path.home() / ".local/bin" / executable("slt")]
    if sys.platform == "win32":
        candidates.append(Path.home() / "AppData/Local/Programs/SimplicityInstaller/resources/slt.exe")
    elif sys.platform == "darwin":
        candidates.append(Path("/Applications/SimplicityInstaller/app/Contents/Resources/slt"))
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return Path(candidate).resolve()
    raise RuntimeError("Install SLT and add its directory to PATH, then rerun setup. See README.md.")


def setup():
    directory = local_path(LOCAL / "slt")
    directory.mkdir(parents=True, exist_ok=True)
    # A failed install must not leave an earlier success stamp in place.
    (directory / "manifest.sha256").unlink(missing_ok=True)
    shutil.copyfile(ROOT / "pkg.lock", directory / "pkg.lock")
    run("Install locked tools", [slt_path(), "install", "-f", directory / "pkg.lock",
                                 "--check-updates=false", "--non-interactive"])
    # Write the stamp only after SLT has installed the locked package set.
    (directory / "manifest.sha256").write_text(digest(ROOT / "pkg.lock"), encoding="utf-8")


def tools():
    # SLT writes actual installation paths here; do not guess SDK cache locations.
    config = LOCAL / "slt/autogen/pkg.slconf"
    stamp = LOCAL / "slt/manifest.sha256"
    if not config.is_file() or not stamp.is_file() or stamp.read_text() != digest(ROOT / "pkg.lock"):
        raise RuntimeError("Run: uv run --locked python tools/firmware.py setup")
    data = tomllib.loads(config.read_text(encoding="utf-8"))
    roots = [Path(path) for path in data["core"]["tool-path"]]

    def find(*names):
        # macOS app bundles and Windows/Linux packages use different layouts.
        matches = {(root / name).resolve() for root in roots for name in names
                   if (root / name).is_file()}
        if len(matches) != 1:
            raise RuntimeError(f"Expected one installed {names[0]}; found {len(matches)}. Rerun setup.")
        return matches.pop().resolve()

    sdk_roots = data["slc"]["sdk-package-path"]
    if len(sdk_roots) != 1:
        raise RuntimeError("Expected the single SDK from pkg.lock. Rerun setup.")
    paths = {"slt": slt_path(), "sdk": Path(sdk_roots[0]),
             "gcc_root": Path(data["toolchain"]["gcc"]),
             "java": find("jre/bin/" + executable("java"), "bin/" + executable("java")),
             "slc": find("slc.jar"),
             "cmake": find("bin/" + executable("cmake"), "CMake.app/Contents/bin/cmake",
                           "Contents/bin/cmake"),
             "ninja": find(executable("ninja"), "bin/" + executable("ninja")),
             "commander": find(executable("commander"), "Contents/MacOS/commander",
                               "../MacOS/commander")}
    # Check installed versions before building, even if other toolchains are on PATH.
    gcc = paths["gcc_root"] / "bin" / executable("arm-none-eabi-gcc")
    version = subprocess.check_output([str(gcc), "-dumpfullversion"], text=True).strip()
    manifest = (paths["sdk"] / "simplicity_sdk.slcs").read_text(encoding="utf-8")
    sdk_version = re.search(r'^sdk_version:\s*[\"\']?([^\"\'\s]+)', manifest, re.MULTILINE)
    if version != GCC_VERSION or not sdk_version or sdk_version[1] != SDK_VERSION:
        raise RuntimeError("SDK or compiler differs from the tested versions. Rerun setup.")
    paths["gcc"] = gcc
    return paths


def environment(paths):
    # Give child processes the locked tools without changing the user's global PATH.
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join(str(p) for p in [paths["slt"].parent, paths["java"].parent,
        paths["gcc"].parent, paths["cmake"].parent, paths["ninja"].parent,
        paths["commander"].parent]) + os.pathsep + env.get("PATH", "")
    env.update(ARM_GCC_DIR=paths["gcc_root"].as_posix(),
               NINJA_EXE_PATH=paths["ninja"].as_posix(), POST_BUILD_EXE=paths["commander"].as_posix())
    return env


def jlink_path():
    # J-Link is installed separately from SLT and supplies the F5 debug server.
    names = JLINK_NAMES[sys.platform]
    for name in names:
        found = shutil.which(name)
        if found:
            return Path(found)
    if sys.platform == "win32":
        bases = [Path(os.environ[key]) / "SEGGER"
                 for key in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")
                 if os.environ.get(key)]
    else:
        bases = JLINK_BASES[sys.platform]
    for base in bases:
        directories = [base / "JLink", *sorted(base.glob("JLink*"), reverse=True)]
        for directory in directories:
            for name in names:
                candidate = directory / name
                if candidate.is_file() and os.access(candidate, os.X_OK):
                    return candidate
    return None


def gdb_path(paths):
    # Distribution GDB avoids dependencies on the toolchain's bundled Python library.
    system_gdb = shutil.which(LINUX_GDB) if sys.platform == "linux" else None
    return Path(system_gdb) if system_gdb else paths["gcc"].parent / executable("arm-none-eabi-gdb")


def workspace(paths, check_debug=False):
    # Absolute, machine-specific paths belong in the ignored local workspace.
    settings = {"starter.uvPath": uv_path().as_posix(),
                "cortex-debug.armToolchainPath": paths["gcc"].parent.as_posix(),
                "cortex-debug.gdbPath": gdb_path(paths).as_posix(),
                "cmake.cmakePath": paths["cmake"].as_posix(),
                "cmake.configureEnvironment": {key: environment(paths)[key]
                    for key in ("ARM_GCC_DIR", "NINJA_EXE_PATH", "POST_BUILD_EXE")}}
    jlink = jlink_path()
    if jlink:
        settings["cortex-debug.JLinkGDBServerPath"] = jlink.as_posix()
    else:
        print("For F5 debugging, install SEGGER J-Link Software and rerun doctor.")
    output = local_path(LOCAL / "starter.code-workspace")
    output.write_text(json.dumps({"folders": [{"path": ".."}], "settings": settings}, indent=2) + "\n",
                      encoding="utf-8")
    print("VS Code: open .local/starter.code-workspace")
    if check_debug:
        if not jlink:
            raise RuntimeError("J-Link GDB Server is missing. Install SEGGER J-Link Software and rerun doctor --debug.")
        try:
            run("GDB version", [gdb_path(paths), "--version"], env=environment(paths))
        except (OSError, RuntimeError) as exc:
            hint = " On Ubuntu/Debian, install gdb-multiarch." if sys.platform == "linux" else ""
            raise RuntimeError(f"GDB could not start.{hint} {exc}") from exc
        print("Debugger tools found. USB access and target connection still require a connected kit.")


def fingerprint(paths):
    # Regenerate when authored sources, recipes, or resolved tool paths change.
    value = hashlib.sha256()
    inputs = [ROOT / "pkg.lock", ROOT / "user.slconf", Path(__file__), ROOT / "tools/app_mode.cmake"]
    inputs += sorted(path for path in (ROOT / "firmware").rglob("*") if path.is_file())
    for path in inputs:
        value.update(path.relative_to(ROOT).as_posix().encode())
        value.update(path.read_bytes())
    value.update(json.dumps({key: str(path) for key, path in paths.items()}, sort_keys=True).encode())
    return value.hexdigest()


def generate(paths, force=False):
    # Students edit firmware/; SLC may replace files under generated/ on any build.
    current = fingerprint(paths)
    stamp = local_path(LOCAL / "slc-generation.json")
    prior = json.loads(stamp.read_text()) if stamp.is_file() else {}
    if force or prior.get("fingerprint") != current or not (PROJECT / "CMakeLists.txt").is_file():
        stamp.unlink(missing_ok=True)
        GENERATED.mkdir(parents=True, exist_ok=True)
        run("Generate firmware", [paths["java"], "-jar", paths["slc"], "generate",
            ROOT / "firmware/series2_starter.slcp", "--slconf", ROOT / "user.slconf",
            "--new-project", "--destination", GENERATED, "--output-type", "cmake",
            "--toolchain", "gcc", "--replace-sources", "--replace-config", "--no-daemon", "--no-color"],
            env=environment(paths))
        # Confirm SLC copied our authored files before accepting this generation.
        for directory in ("src", "include"):
            for source in (ROOT / "firmware" / directory).rglob("*"):
                if source.is_file() and source.suffix.lower() in SOURCE_SUFFIXES:
                    copied = GENERATED / source.relative_to(ROOT / "firmware")
                    if not copied.is_file() or copied.read_bytes() != source.read_bytes():
                        raise RuntimeError(f"Generated source differs from firmware: {copied}")
        shutil.copyfile(ROOT / "tools/app_mode.cmake", PROJECT / "series2_starter_project.cmake")
        # Use the exact SLT-resolved paths, including when other versions are installed.
        (PROJECT / "autogen_toolchain.cmake").write_text(
            f'set(DEFAULT_TOOLCHAIN_DIR "{paths["gcc"].parent.as_posix()}/")\n'
            f'set(DEFAULT_NINJA_RUNTIME_PATH "{paths["ninja"].as_posix()}")\n'
            f'set(DEFAULT_POST_BUILD_EXE "{paths["commander"].as_posix()}")\n', encoding="utf-8")
        stamp.write_text(json.dumps({"fingerprint": current}, indent=2) + "\n", encoding="utf-8")
    return current


def write_intellisense(destination):
    # Keep SDK entries and add aliases for the authored files students edit.
    # This editor-only database does not change which files CMake compiles.
    entries = json.loads((destination / INTELLISENSE_DATABASE).read_text(encoding="utf-8"))
    for entry in entries[:]:
        source = Path(entry["file"]).resolve()
        if not source.is_relative_to(GENERATED / "src"):
            continue
        authored = ROOT / "firmware" / source.relative_to(GENERATED)
        if authored.is_file():
            mapped = entry.copy()
            mapped["file"] = str(authored)
            mapped["command"] = entry["command"].replace(str(source), str(authored)).replace(
                source.as_posix(), authored.as_posix()).replace(
                (PROJECT / "../include").as_posix(), (ROOT / "firmware/include").as_posix())
            entries.append(mapped)
    (LOCAL / INTELLISENSE_DATABASE).write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")


def build(paths, mode):
    # Separate build directories keep each power mode's executable and symbols.
    source_hash = generate(paths)
    destination = local_path(ROOT / "build" / mode)
    env = environment(paths)
    # Refresh CMake's compiler cache so locked toolchain upgrades take effect.
    run(f"Configure {mode}", [paths["cmake"], "--fresh", "--preset", "project", "-B", destination,
        f"-DAPP_MODE={MODES[mode]}", "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON"], cwd=PROJECT, env=env)
    run(f"Build {mode}", [paths["cmake"], "--build", destination, "--config", "base",
        "--target", "series2_starter", "--parallel", BUILD_JOBS], cwd=PROJECT, env=env)
    binary = destination / "base/series2_starter.out"
    if not binary.is_file():
        raise RuntimeError(f"Expected executable is absent: {binary}")
    run(f"Size {mode}", [paths["gcc"].parent / executable("arm-none-eabi-size"), "-A", binary], env=env)
    # Associate this executable with its source inputs for later capture comparisons.
    (LOCAL / f"build-{mode}.json").write_text(json.dumps({"mode": mode, "APP_MODE": MODES[mode],
        "source_fingerprint": source_hash, "binary": str(binary), "sha256": digest(binary)}, indent=2) + "\n",
        encoding="utf-8")
    write_intellisense(destination)
    print(f"Built {binary.relative_to(ROOT)}; HEX, BIN, S37 and MAP files are beside it.")


def main():
    # Each CLI subcommand is also available as a VS Code task where appropriate.
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("setup", "doctor", "generate", "build", "commander"):
        command = commands.add_parser(name)
        if name == "build":
            command.add_argument("--mode", choices=MODES, default=DEFAULT_MODE)
        elif name == "doctor":
            command.add_argument("--debug", action="store_true", help="also check J-Link and GDB tools")
    args = parser.parse_args()
    if sys.platform not in ("win32", "darwin", "linux"):
        raise RuntimeError("Supported hosts: Windows, macOS and Linux.")
    for path in (LOCAL, LOCAL / "slt", LOCAL / "logs", GENERATED, PROJECT, ROOT / "build"):
        local_path(path)
    if args.command == "setup":
        setup()
    paths = tools()
    LOCAL.mkdir(parents=True, exist_ok=True)
    if args.command in ("setup", "doctor"):
        run("SLT version", [paths["slt"], "--version"])
        run("SLC version", [paths["java"], "-jar", paths["slc"], "--version"])
        for name in ("cmake", "ninja", "commander"):
            run(f"{name} version", [paths[name], "--version"])
        print(f"SDK {SDK_VERSION}; Arm GCC {GCC_VERSION}")
        (LOCAL / "toolchain.json").write_text(json.dumps({key: str(path) for key, path in paths.items()},
                                                       indent=2) + "\n", encoding="utf-8")
        workspace(paths, check_debug=getattr(args, "debug", False))
    elif args.command == "generate":
        generate(paths, force=True)
    elif args.command == "commander":
        # Open the vendor GUI; flashing still requires selecting a kit and image.
        subprocess.Popen([str(paths["commander"])], cwd=paths["commander"].parent,
                         env=environment(paths))
    else:
        build(paths, args.mode)


if __name__ == "__main__":
    # Imported by tests and energy_profile.py without running the CLI.
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Setup error: {exc}", file=sys.stderr)
        raise SystemExit(1)
