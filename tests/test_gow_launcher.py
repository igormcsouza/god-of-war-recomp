"""Synthetic tests for the ISO reader and Linux launch preparation."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch


MODULE = Path(__file__).resolve().parents[1] / "tools/linux/gow_launcher.py"
spec = importlib.util.spec_from_file_location("gow_launcher", MODULE)
assert spec is not None and spec.loader is not None
import sys

launcher = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = launcher
spec.loader.exec_module(launcher)


def both16(value: int) -> bytes:
    return value.to_bytes(2, "little") + value.to_bytes(2, "big")


def both32(value: int) -> bytes:
    return value.to_bytes(4, "little") + value.to_bytes(4, "big")


def record(name: bytes, extent: int, size: int, *, directory: bool = False) -> bytes:
    length = 33 + len(name) + (len(name) % 2 == 0)
    data = bytearray(length)
    data[0] = length
    data[2:10] = both32(extent)
    data[10:18] = both32(size)
    data[25] = 2 if directory else 0
    data[28:32] = both16(1)
    data[32] = len(name)
    data[33:33 + len(name)] = name
    return bytes(data)


def make_iso(path: Path, *, boot: str = "SCUS_973.99", bad_name: bytes | None = None,
             corrupt_extent: bool = False) -> bytes:
    elf = b"\x7fELF" + b"recomp-fixture"
    contents = {
        b"SYSTEM.CNF;1": f"BOOT2 = cdrom0:\\{boot};1\r\n".encode(),
        b"SCUS_973.99;1": elf,
        b"SMPD_IOP.IRX;1": b"smpd",
        b"989NOMID.IRX;1": b"989snd",
        b"LIBSD.IRX;1": b"libsd",
    }
    if bad_name:
        contents[bad_name] = b"bad"
    sectors = 64
    image = bytearray(sectors * launcher.SECTOR)
    pvd = bytearray(launcher.SECTOR)
    pvd[:7] = b"\x01CD001\x01"
    pvd[80:88] = both32(sectors)
    pvd[128:132] = both16(launcher.SECTOR)
    root = bytearray(launcher.SECTOR)
    entries = [record(b"\x00", 20, launcher.SECTOR, directory=True),
               record(b"\x01", 20, launcher.SECTOR, directory=True)]
    for index, (name, content) in enumerate(contents.items(), start=21):
        extent = 80 if corrupt_extent and name.startswith(b"SCUS") else index
        entries.append(record(name, extent, len(content)))
        image[index * launcher.SECTOR:index * launcher.SECTOR + len(content)] = content
    root[:sum(map(len, entries))] = b"".join(entries)
    pvd[156:190] = record(b"\x00", 20, launcher.SECTOR, directory=True)
    image[16 * launcher.SECTOR:17 * launcher.SECTOR] = pvd
    image[17 * launcher.SECTOR:17 * launcher.SECTOR + 7] = b"\xffCD001\x01"
    image[20 * launcher.SECTOR:21 * launcher.SECTOR] = root
    path.write_bytes(image)
    return elf


class LauncherTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.iso = self.root / "my disc with spaces.iso"
        self.cache = self.root / "private cache"

    def test_prepare_reuses_valid_cache_and_repairs_corruption(self) -> None:
        elf_bytes = make_iso(self.iso)
        import hashlib

        with patch.object(launcher, "ELF_SHA256", hashlib.sha256(elf_bytes).hexdigest()):
            elf = launcher.prepare(self.iso, self.cache)
            self.assertEqual(elf.read_bytes(), elf_bytes)
            self.assertEqual((elf.parent / "IOP_MOD/smpd_iop.irx").read_bytes(), b"smpd")
            self.assertEqual(launcher.prepare(self.iso, self.cache), elf)
            (elf.parent / "IOP_MOD/smpd_iop.irx").write_bytes(b"roto")
            self.assertEqual(launcher.prepare(self.iso, self.cache), elf)
            self.assertEqual((elf.parent / "IOP_MOD/smpd_iop.irx").read_bytes(), b"smpd")
            self.assertEqual(stat.S_IMODE(self.cache.stat().st_mode), 0o700)
            manifest = json.loads((elf.parent / "manifest.json").read_text())
            self.assertEqual(manifest["sha256"][launcher.ELF_NAME], launcher.ELF_SHA256)

    def test_changed_iso_invalidates_cache(self) -> None:
        elf_bytes = make_iso(self.iso)
        import hashlib

        with patch.object(launcher, "ELF_SHA256", hashlib.sha256(elf_bytes).hexdigest()):
            first = launcher.prepare(self.iso, self.cache)
            old = self.iso.stat()
            os.utime(self.iso, ns=(old.st_atime_ns, old.st_mtime_ns + 1_000_000))
            second = launcher.prepare(self.iso, self.cache)
            self.assertNotEqual(first, second)

    def test_wrong_revision_or_elf_hash(self) -> None:
        make_iso(self.iso, boot="SLUS_000.00")
        with self.assertRaisesRegex(launcher.IsoError, "revision"):
            launcher.prepare(self.iso, self.cache)
        make_iso(self.iso)
        with self.assertRaisesRegex(launcher.IsoError, "SHA-256"):
            launcher.prepare(self.iso, self.cache)

    def test_rejects_traversal_and_corrupt_extent(self) -> None:
        make_iso(self.iso, bad_name=b"../ESCAPE;1")
        with self.assertRaisesRegex(launcher.IsoError, "unsafe"):
            launcher.prepare(self.iso, self.cache)
        make_iso(self.iso, corrupt_extent=True)
        with self.assertRaisesRegex(launcher.IsoError, "outside ISO"):
            launcher.prepare(self.iso, self.cache)
        self.assertFalse((self.root / "ESCAPE").exists())

    def test_launch_passes_paths_and_iso_to_runner(self) -> None:
        elf_bytes = make_iso(self.iso)
        import hashlib

        runner = self.root / "runner con espacios" / "ps2EntryRunner"
        runner.parent.mkdir()
        runner.write_text("#!/bin/sh\nexit 0\n")
        runner.chmod(0o755)
        with patch.object(launcher, "ELF_SHA256", hashlib.sha256(elf_bytes).hexdigest()), \
             patch.dict(os.environ, {"XDG_CACHE_HOME": str(self.cache)}), \
             patch.object(launcher.subprocess, "call", return_value=7) as call:
            self.assertEqual(launcher.main(["--iso", str(self.iso), "--runner", str(runner)]), 7)
        args, kwargs = call.call_args
        self.assertEqual(args[0][0], str(runner))
        self.assertEqual(Path(args[0][1]).name, launcher.ELF_NAME)
        self.assertEqual(kwargs["cwd"], Path(args[0][1]).parent)
        self.assertEqual(kwargs["env"]["GOW_ISO"], str(self.iso))

    def test_prepare_only_never_starts_runtime_or_compiler(self) -> None:
        elf_bytes = make_iso(self.iso)
        import hashlib

        with patch.object(launcher, "ELF_SHA256", hashlib.sha256(elf_bytes).hexdigest()), \
             patch.dict(os.environ, {"XDG_CACHE_HOME": str(self.cache)}), \
             patch.object(launcher.subprocess, "call") as call, \
             patch.object(launcher.subprocess, "run") as run, \
             patch.object(launcher.subprocess, "Popen") as popen:
            self.assertEqual(launcher.main(["--iso", str(self.iso), "--prepare-only"]), 0)
            call.assert_not_called()
            run.assert_not_called()
            popen.assert_not_called()


class SettingsTest(unittest.TestCase):
    def test_roundtrip_defaults_and_bad_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "settings.json"
            self.assertEqual(launcher.load_settings(path), launcher.DEFAULT_SETTINGS)
            chosen = dict(launcher.DEFAULT_SETTINGS, iso="/x.iso", pad_index=2, raster_threads=4)
            launcher.save_settings(chosen, path)
            self.assertEqual(launcher.load_settings(path), chosen)
            path.write_text('{"pad_index": 9, "resolution_scale": 7, "debug_ui": "yes", "junk": 1}')
            self.assertEqual(launcher.load_settings(path), launcher.DEFAULT_SETTINGS)
            path.write_text("not json")
            self.assertEqual(launcher.load_settings(path), launcher.DEFAULT_SETTINGS)

    def test_settings_path_uses_xdg(self) -> None:
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": "/cfg"}):
            self.assertEqual(launcher.settings_path(), Path("/cfg/gow-one-recomp/settings.json"))

    def test_env_mapping(self) -> None:
        self.assertEqual(launcher.settings_to_env(launcher.DEFAULT_SETTINGS), {})
        env = launcher.settings_to_env(dict(launcher.DEFAULT_SETTINGS, fullscreen=True, debug_ui=True,
                                            pad_index=0, raster_threads=3, resolution_scale=3))
        self.assertEqual(env, {"GOW_FULLSCREEN": "1", "GOW_DEBUG_UI": "1", "GOW_PAD_INDEX": "0",
                               "PS2X_GS_RASTER_THREADS": "3"})

    def test_gpu_env_mapping(self) -> None:
        self.assertNotIn("PS2X_VK_DEVICE", launcher.settings_to_env(launcher.DEFAULT_SETTINGS))
        self.assertEqual(launcher.settings_to_env(dict(launcher.DEFAULT_SETTINGS, gpu="NVIDIA")),
                         {"PS2X_VK_DEVICE": "NVIDIA"})
        with patch.object(launcher.subprocess, "run", side_effect=FileNotFoundError):
            self.assertEqual(launcher.detect_gpus(), [])

    def test_mute_audio_env_mapping(self) -> None:
        self.assertNotIn("GOW_AUDIO", launcher.settings_to_env(dict(launcher.DEFAULT_SETTINGS, mute_audio=False)))
        self.assertEqual(launcher.settings_to_env(dict(launcher.DEFAULT_SETTINGS, mute_audio=True)),
                         {"GOW_AUDIO": "0"})

    def test_mute_audio_roundtrip_and_old_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            launcher.save_settings(dict(launcher.DEFAULT_SETTINGS, mute_audio=True), path)
            self.assertTrue(launcher.load_settings(path)["mute_audio"])
            # Settings written before the key existed: default False, other keys kept.
            path.write_text('{"debug_ui": true, "pad_index": 1}')
            loaded = launcher.load_settings(path)
            self.assertIs(loaded["mute_audio"], False)
            self.assertTrue(loaded["debug_ui"])
            path.write_text('{"mute_audio": "yes"}')
            self.assertIs(launcher.load_settings(path)["mute_audio"], False)

    def test_mute_flag_is_one_run_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            iso = Path(tmp) / "d.iso"
            elf = make_iso(iso)
            import hashlib
            runner = Path(tmp) / "r"
            runner.write_text("#!/bin/sh\n")
            runner.chmod(0o755)
            cfg = Path(tmp) / "cfg"
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(cfg), "XDG_CACHE_HOME": tmp + "/c"}), \
                 patch.object(launcher, "ELF_SHA256", hashlib.sha256(elf).hexdigest()), \
                 patch.object(launcher.subprocess, "call", return_value=0) as call:
                launcher.save_settings(dict(launcher.DEFAULT_SETTINGS, iso=str(iso)))
                self.assertEqual(launcher.main(["--last", "--mute", "--runner", str(runner)]), 0)
                self.assertEqual(call.call_args[1]["env"]["GOW_AUDIO"], "0")
                self.assertFalse(launcher.load_settings()["mute_audio"])

    def test_last_uses_saved_settings_without_gui(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            iso = Path(tmp) / "d.iso"
            elf = make_iso(iso)
            import hashlib
            runner = Path(tmp) / "r"
            runner.write_text("#!/bin/sh\n")
            runner.chmod(0o755)
            cfg = Path(tmp) / "cfg"
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(cfg), "XDG_CACHE_HOME": tmp + "/c"}), \
                 patch.object(launcher, "ELF_SHA256", hashlib.sha256(elf).hexdigest()), \
                 patch.object(launcher, "settings_window") as win, \
                 patch.object(launcher.subprocess, "call", return_value=0) as call:
                launcher.save_settings(dict(launcher.DEFAULT_SETTINGS, iso=str(iso), debug_ui=True))
                self.assertEqual(launcher.main(["--last", "--runner", str(runner)]), 0)
                win.assert_not_called()
            self.assertEqual(call.call_args[1]["env"]["GOW_DEBUG_UI"], "1")


if __name__ == "__main__":
    unittest.main()
