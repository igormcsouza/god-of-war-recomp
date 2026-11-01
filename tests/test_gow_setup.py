import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "linux"))
import gow_app  # noqa: E402
import gow_setup as setup  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


class SetupTest(unittest.TestCase):
    def test_version_file_is_semver(self) -> None:
        self.assertRegex(setup.version(), r"^\d+\.\d+\.\d+")

    def test_runtime_lives_under_xdg_data_home_per_version(self) -> None:
        with patch.dict(os.environ, {"XDG_DATA_HOME": "/data"}):
            self.assertEqual(setup.data_dir(), Path("/data/gow-one-recomp") / setup.version())
            self.assertEqual(setup.installed_runner(), setup.data_dir() / "bin" / "ps2EntryRunner")

    def test_missing_tools_reported_without_running_anything(self) -> None:
        out: list[str] = []
        with patch.object(setup.shutil, "which", return_value=None), \
             patch.object(setup.subprocess, "Popen") as popen:
            self.assertEqual(setup.run_steps(Path("/nope.iso"), out.append), 2)
        popen.assert_not_called()
        self.assertIn("Missing tools", "".join(out))
        self.assertIn("apt install", "".join(out))

    def test_steps_build_twice_with_capture_between_and_install_last(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict(os.environ, {"XDG_DATA_HOME": tmp}), \
             patch.object(setup.launcher, "prepare", return_value=Path("/cache/SCUS_973.99")):
            plan = setup.steps(Path("/x.iso"))
        titles = [title for title, _ in plan]
        self.assertEqual(len(plan), 3)
        self.assertIn("compilar_linux.py", plan[0][1][1])
        self.assertIn("capture_microcode.py", plan[1][1][1])
        self.assertIn("--install", plan[2][1])
        self.assertNotIn("--install", plan[0][1])
        self.assertTrue(titles[0].startswith("Build 1/2") and titles[2].startswith("Build 2/2"))
        self.assertIn("--work-dir", plan[0][1])

    def test_steps_run_in_a_data_folder_that_exists_on_a_fresh_machine(self) -> None:
        seen: list[bool] = []

        class Proc:
            stdout = iter([])
            returncode = 0

            def wait(self) -> int:
                return 0

        def popen(command, **kwargs):
            seen.append(Path(kwargs["cwd"]).is_dir())
            return Proc()

        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"XDG_DATA_HOME": tmp + "/fresh"}), \
             patch.object(setup.shutil, "which", return_value="/usr/bin/x"), \
             patch.object(setup, "steps", return_value=[("one", ["a"])]), \
             patch.object(setup.subprocess, "Popen", side_effect=popen):
            self.assertEqual(setup.run_steps(Path("/x.iso"), lambda line: None), 0)
        self.assertEqual(seen, [True])

    def test_failed_step_stops_the_setup(self) -> None:
        class Proc:
            stdout = iter(["line\n"])
            returncode = 3

            def wait(self) -> int:
                return 3

        out: list[str] = []
        with patch.object(setup.shutil, "which", return_value="/usr/bin/x"), \
             patch.object(setup, "steps", return_value=[("one", ["a"]), ("two", ["b"])]), \
             patch.object(setup.subprocess, "Popen", return_value=Proc()) as popen:
            self.assertEqual(setup.run_steps(Path("/x.iso"), out.append), 1)
        self.assertEqual(popen.call_count, 1)
        self.assertIn("Step 1 failed", "".join(out))


class AppTest(unittest.TestCase):
    def test_self_test_runs_without_a_display_or_runtime(self) -> None:
        proc = subprocess.run([sys.executable, str(ROOT / "tools/linux/gow_app.py"), "--self-test"],
                              capture_output=True, text=True, env=dict(os.environ, XDG_DATA_HOME=tempfile.gettempdir() + "/none"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("tkinter OK", proc.stdout)
        self.assertIn("not built yet", proc.stdout)

    def test_installed_runtime_goes_straight_to_the_launcher(self) -> None:
        with patch.object(gow_app.setup, "installed_runner") as runner, \
             patch.object(gow_app.launcher, "main", return_value=0) as launcher_main, \
             patch.object(gow_app.setup, "main") as setup_main:
            runner.return_value = Path(__file__)  # any existing file
            self.assertEqual(gow_app.main(["--last"]), 0)
        setup_main.assert_not_called()
        self.assertEqual(launcher_main.call_args[0][0][-2], "--runner")

    def test_missing_runtime_runs_the_setup_first(self) -> None:
        with patch.object(gow_app.setup, "installed_runner", return_value=Path("/nonexistent/ps2EntryRunner")), \
             patch.object(gow_app.setup, "main", return_value=1) as setup_main, \
             patch.object(gow_app.launcher, "main") as launcher_main:
            self.assertEqual(gow_app.main([]), 1)
        setup_main.assert_called_once()
        launcher_main.assert_not_called()


if __name__ == "__main__":
    unittest.main()
