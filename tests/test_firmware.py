"""Host setup regressions; fixture tests do not execute foreign tool binaries."""

from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

# Import the helper as a module so tests can replace tool discovery and subprocesses.
SPEC = importlib.util.spec_from_file_location(
    "firmware", Path(__file__).resolve().parents[1] / "tools/firmware.py")
firmware = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(firmware)


class FirmwareTests(unittest.TestCase):
    def setUp(self):
        # Exercise paths with spaces without touching the real SDK or repository outputs.
        temporary = tempfile.TemporaryDirectory(prefix="starter paths with spaces ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        for name, path in {"ROOT": self.root, "LOCAL": self.root / ".local",
                           "GENERATED": self.root / "generated",
                           "PROJECT": self.root / "generated/cmake_gcc"}.items():
            patcher = patch.object(firmware, name, path)
            patcher.start()
            self.addCleanup(patcher.stop)

    def file(self, name, content=""):
        # Fixtures need only exist and be executable; no foreign binary is launched.
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)
        return path

    def installed_tools(self, host):
        # Vendor layouts: Java apack, CMake Conan recipe, Commander app bundle.
        layouts = {
            "win32": {"java": "java/jre/bin/java.exe", "cmake": "cmake/bin/cmake.exe",
                      "ninja": "ninja/ninja.exe", "commander": "commander/commander.exe",
                      "gcc": "gcc/bin/arm-none-eabi-gcc.exe", "slt": "slt.exe"},
            "darwin": {"java": "java/jre/bin/java",
                       "cmake": "cmake/CMake.app/Contents/bin/cmake", "ninja": "ninja/ninja",
                       "commander": "commander/Contents/MacOS/commander",
                       "gcc": "gcc/bin/arm-none-eabi-gcc", "slt": "slt"},
            "linux": {"java": "java/jre/bin/java", "cmake": "cmake/bin/cmake",
                      "ninja": "ninja/ninja", "commander": "commander/commander",
                      "gcc": "gcc/bin/arm-none-eabi-gcc", "slt": "slt"},
        }
        paths = {name: self.file(f"{host}/{relative}") for name, relative in layouts[host].items()}
        paths["slc"] = self.file(f"{host}/slc/slc.jar")
        paths["gcc_root"] = self.root / host / "gcc"
        paths["sdk"] = self.root / host / "sdk"
        self.file(f"{host}/sdk/simplicity_sdk.slcs", "sdk_version: '2026.6.1'\n")
        roots = [self.root / host / name for name in ("java", "cmake", "ninja", "commander", "slc")]
        if host == "darwin":
            roots[3] = roots[3] / "Contents/Resources"
        for root in roots:
            root.mkdir(parents=True, exist_ok=True)
        quote = lambda path: json.dumps(path.as_posix())
        self.file("pkg.lock", 'version = "0"\n')
        # Reproduce SLT's configuration and the success stamp checked by tools().
        self.file(".local/slt/manifest.sha256", firmware.digest(self.root / "pkg.lock"))
        self.file(".local/slt/autogen/pkg.slconf",
                  "[core]\ntool-path = [" + ",".join(map(quote, roots)) + "]\n"
                  "[slc]\nsdk-package-path = [" + quote(paths["sdk"]) + "]\n"
                  "[toolchain]\ngcc = " + quote(paths["gcc_root"]) + "\n")
        return paths

    def test_locked_tool_discovery_on_each_host(self):
        # Mock only the version query; discover paths through the production helper.
        for host in ("win32", "darwin", "linux"):
            with self.subTest(host=host):
                expected = self.installed_tools(host)
                with patch.object(sys, "platform", host), \
                     patch.object(firmware, "slt_path", return_value=expected["slt"]), \
                     patch.object(subprocess, "check_output", return_value="14.2.1\n") as compiler:
                    self.assertEqual(firmware.tools(), expected)
                    compiler.assert_called_once_with([str(expected["gcc"]), "-dumpfullversion"], text=True)

    def test_slt_fallback_has_host_executable_name(self):
        for host, filename in (("win32", "slt.exe"), ("darwin", "slt"), ("linux", "slt")):
            with self.subTest(host=host):
                home = self.root / host
                expected = self.file(f"{host}/.local/bin/{filename}")
                with patch.object(sys, "platform", host), patch.object(Path, "home", return_value=home), \
                     patch.object(firmware.shutil, "which", return_value=None):
                    self.assertEqual(firmware.slt_path(), expected)

    def test_uv_fallback_without_path_on_each_host(self):
        # Models an editor opened before uv's installer updated the user's PATH.
        for host, filename in (("win32", "uv.exe"), ("darwin", "uv"), ("linux", "uv")):
            with self.subTest(host=host):
                home = self.root / host
                expected = self.file(f"{host}/.local/bin/{filename}")
                with patch.object(sys, "platform", host), patch.object(Path, "home", return_value=home), \
                     patch.object(firmware.shutil, "which", return_value=None):
                    self.assertEqual(firmware.uv_path(), expected)

    def test_uv_custom_installation_on_path(self):
        expected = self.file("custom tools/uv.exe")
        with patch.object(firmware.shutil, "which", return_value=str(expected)):
            self.assertEqual(firmware.uv_path(), expected)

    def test_macos_commander_app_root_and_executable_directory(self):
        paths = self.installed_tools("darwin")
        config = self.root / ".local/slt/autogen/pkg.slconf"
        original = config.read_text(encoding="utf-8")
        for suffix in ("", "/Contents/MacOS"):
            with self.subTest(suffix=suffix):
                config.write_text(original.replace("/commander/Contents/Resources",
                                                    "/commander" + suffix), encoding="utf-8")
                with patch.object(sys, "platform", "darwin"), \
                     patch.object(firmware, "slt_path", return_value=paths["slt"]), \
                     patch.object(subprocess, "check_output", return_value="14.2.1\n"):
                    self.assertEqual(firmware.tools()["commander"], paths["commander"])

    def test_jlink_default_locations_and_cli_names(self):
        cases = (("win32", "C:/Program Files/SEGGER/JLink/JLinkGDBServerCL.exe"),
                 ("darwin", "/Applications/SEGGER/JLink/JLinkGDBServerCLExe"),
                 ("linux", "/opt/SEGGER/JLink/JLinkGDBServer"))
        for host, name in cases:
            with self.subTest(host=host):
                expected = Path(name)
                with patch.object(sys, "platform", host), \
                     patch.dict(firmware.os.environ, {"ProgramFiles": "C:/Program Files"}), \
                     patch.object(firmware.shutil, "which", return_value=None), \
                     patch.object(Path, "glob", return_value=[]), \
                     patch.object(Path, "is_file", autospec=True, side_effect=lambda p: p == expected), \
                     patch.object(firmware.os, "access", return_value=True):
                    self.assertEqual(firmware.jlink_path(), expected)

    def test_workspace_uses_linux_system_gdb_and_local_paths(self):
        # Machine-specific debugger paths should be written to the local workspace.
        paths = self.installed_tools("linux")
        gdb = self.file("system bin/gdb-multiarch")
        jlink = self.file("SEGGER/JLinkGDBServer")
        with patch.object(sys, "platform", "linux"), \
             patch.object(firmware.shutil, "which", return_value=str(gdb)), \
             patch.object(firmware, "uv_path", return_value=self.root / "custom tools/uv"), \
             patch.object(firmware, "jlink_path", return_value=jlink), redirect_stdout(io.StringIO()):
            firmware.workspace(paths)
        data = json.loads((self.root / ".local/starter.code-workspace").read_text())
        self.assertEqual(data["folders"], [{"path": ".."}])
        self.assertEqual(data["settings"]["starter.uvPath"], (self.root / "custom tools/uv").as_posix())
        self.assertEqual(data["settings"]["cortex-debug.gdbPath"], gdb.as_posix())
        self.assertEqual(data["settings"]["cortex-debug.JLinkGDBServerPath"], jlink.as_posix())
        self.assertEqual(data["settings"]["cmake.cmakePath"], paths["cmake"].as_posix())

    def test_intellisense_uses_authored_files_and_current_mode(self):
        # Keep real SDK/generated entries and map only student-authored source aliases.
        source = self.file("generated/src/app.c")
        authored = self.file("firmware/src/app.c")
        self.file("firmware/include/app_config.h")
        sdk = self.file("sdk/driver.c")
        destination = self.root / "build/demo"
        destination.mkdir(parents=True)
        (self.root / ".local").mkdir()
        # Building another mode must update the editor's APP_MODE and include paths.
        for mode in (3, 2):
            for source_name in (str(source), source.as_posix()):
                with self.subTest(mode=mode, source_name=source_name):
                    include = (firmware.PROJECT / "../include").as_posix()
                    command = f'gcc -DAPP_MODE={mode} -I"{include}" -Iautogen -c "{source_name}"'
                    entries = [{"file": str(source), "directory": str(destination), "command": command},
                               {"file": str(sdk), "directory": str(destination), "command": "gcc -c driver.c"}]
                    database = destination / firmware.INTELLISENSE_DATABASE
                    database.write_text(json.dumps(entries), encoding="utf-8")
                    firmware.write_intellisense(destination)
                    actual = json.loads((firmware.LOCAL / firmware.INTELLISENSE_DATABASE).read_text())
                    self.assertEqual(actual[:2], entries)
                    self.assertEqual(len(actual), 3)
                    self.assertEqual(actual[2]["file"], str(authored))
                    self.assertIn(f"-DAPP_MODE={mode}", actual[2]["command"])
                    self.assertIn((self.root / "firmware/include").as_posix(), actual[2]["command"])
                    self.assertIn("-Iautogen", actual[2]["command"])
                    self.assertNotIn("generated/src", actual[2]["command"].replace("\\", "/"))

    def test_debug_check_reports_missing_gdb_libraries(self):
        # Turn a tool startup failure into an actionable Linux installation hint.
        paths = self.installed_tools("linux")
        with patch.object(sys, "platform", "linux"), \
             patch.object(firmware.shutil, "which", return_value=None), \
             patch.object(firmware, "uv_path", return_value=self.root / "uv"), \
             patch.object(firmware, "jlink_path", return_value=self.root / "JLinkGDBServer"), \
             patch.object(firmware, "run", side_effect=RuntimeError("libpython3.8.so missing")), \
             redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "install gdb-multiarch"):
                firmware.workspace(paths, check_debug=True)

    def test_failed_setup_invalidates_previous_success(self):
        # Failed downloads must block later builds instead of reusing an old success stamp.
        self.installed_tools("win32")
        with patch.object(firmware, "slt_path", return_value=self.root / "slt.exe"), \
             patch.object(firmware, "run", side_effect=RuntimeError("download failed")):
            with self.assertRaisesRegex(RuntimeError, "download failed"):
                firmware.setup()
        self.assertFalse((self.root / ".local/slt/manifest.sha256").exists())
        with self.assertRaisesRegex(RuntimeError, "firmware.py setup"):
            firmware.tools()

    def test_run_preserves_arguments_with_spaces_and_shell_characters(self):
        # Launch the current Python interpreter and inspect its literal arguments.
        arguments = ["path with spaces", "literal $HOME", "a;b", "it's quoted"]
        for host in ("win32", "darwin", "linux"):
            with self.subTest(host=host), patch.object(sys, "platform", host), redirect_stdout(io.StringIO()):
                output = firmware.run("Arguments", [sys.executable, "-c",
                    "import json,sys; print(json.dumps(sys.argv[1:]))", *arguments], cwd=self.root)
                self.assertEqual(json.loads(output), arguments)

    def generation_fixture(self):
        # Model SLC copying authored code, including nested source/header paths.
        paths = self.installed_tools("win32")
        self.file("tools/app_mode.cmake")
        self.file("generated/cmake_gcc/CMakeLists.txt")
        for name in ("src/app.c", "include/app.h", "src/drivers/sensor.c", "include/drivers/sensor.h"):
            content = f"/* {name} */\n"
            self.file("firmware/" + name, content)
            self.file("generated/" + name, content)
        return paths

    def test_generation_ignores_metadata_and_editor_backups(self):
        paths = self.generation_fixture()
        for name in ("src/.DS_Store", "include/.DS_Store", "src/.app.c.swp", "src/app.c~",
                     "include/app.h.bak", "include/drivers/.sensor.h.swo"):
            self.file("firmware/" + name, "not registered with SLC")
        with patch.object(firmware, "fingerprint", return_value="authored-inputs"), \
             patch.object(firmware, "run", return_value=""):
            self.assertEqual(firmware.generate(paths, force=True), "authored-inputs")
        self.assertEqual(json.loads((firmware.LOCAL / "slc-generation.json").read_text()),
                         {"fingerprint": "authored-inputs"})

    def test_generation_rejects_missing_or_mismatched_authored_code(self):
        for name in ("src/app.c", "include/app.h", "src/drivers/sensor.c", "include/drivers/sensor.h"):
            for failure in ("missing", "mismatch"):
                with self.subTest(name=name, failure=failure):
                    paths = self.generation_fixture()
                    copied = (firmware.GENERATED / name).resolve()
                    self.assertTrue(copied.is_relative_to(self.root))
                    if failure == "missing":
                        copied.unlink()
                    else:
                        copied.write_text("stale generated copy", encoding="utf-8")
                    with patch.object(firmware, "fingerprint", return_value="authored-inputs"), \
                         patch.object(firmware, "run", return_value=""):
                        with self.assertRaises(RuntimeError) as error:
                            firmware.generate(paths, force=True)
                    self.assertIn(str(copied), str(error.exception))
                    self.assertFalse((firmware.LOCAL / "slc-generation.json").exists())


if __name__ == "__main__":
    unittest.main()
