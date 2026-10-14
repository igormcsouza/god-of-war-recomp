#!/usr/bin/env python3
"""Prepare a personal SCUS-97399 ISO and start the native Linux runner."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass


SECTOR = 2048
ELF_NAME = "SCUS_973.99"
ELF_SHA256 = "ec9397d252f14d4412daffaad6be1f1931769e56222b5dbb9b39a947fc8ad71c"
MAX_EXTRACTED_FILE = 64 * 1024 * 1024
MAX_EXTRACTED_TOTAL = 256 * 1024 * 1024
CACHE_VERSION = 2


class IsoError(ValueError):
    """The image has an unsupported format or game revision."""


def _both16(data: bytes) -> int:
    if len(data) != 4 or int.from_bytes(data[:2], "little") != int.from_bytes(data[2:], "big"):
        raise IsoError("inconsistent 16-bit ISO integer")
    return int.from_bytes(data[:2], "little")


def _both32(data: bytes) -> int:
    if len(data) != 8 or int.from_bytes(data[:4], "little") != int.from_bytes(data[4:], "big"):
        raise IsoError("inconsistent 32-bit ISO integer")
    return int.from_bytes(data[:4], "little")


@dataclass(frozen=True)
class Entry:
    name: str
    extent: int
    size: int
    directory: bool


class IsoImage:
    """ISO 9660 reader for 2048-byte sectors and root files."""

    def __init__(self, path: Path):
        self.path = path
        self.file = path.open("rb")
        try:
            self.length = path.stat().st_size
            if self.length < 18 * SECTOR or self.length % SECTOR:
                raise IsoError("truncated image or unsupported ISO sector size")
            pvd = self._read_at(16 * SECTOR, SECTOR)
            if pvd[:7] != b"\x01CD001\x01":
                raise IsoError("ISO 9660 primary volume descriptor not found")
            if _both16(pvd[128:132]) != SECTOR:
                raise IsoError("unsupported ISO sector size")
            volume_sectors = _both32(pvd[80:88])
            if volume_sectors < 18 or volume_sectors * SECTOR > self.length:
                raise IsoError("invalid ISO volume size")
            self.volume_length = volume_sectors * SECTOR
            self.root = self._entry(pvd[156:190])
            if not self.root.directory:
                raise IsoError("invalid ISO root directory")
            self._check_bounds(self.root)
        except BaseException:
            self.file.close()
            raise

    def __enter__(self) -> IsoImage:
        return self

    def __exit__(self, *_: object) -> None:
        self.file.close()

    def _read_at(self, offset: int, size: int) -> bytes:
        self.file.seek(offset)
        data = self.file.read(size)
        if len(data) != size:
            raise IsoError("truncated ISO image")
        return data

    def _check_bounds(self, entry: Entry) -> None:
        offset = entry.extent * SECTOR
        if entry.size < 0 or offset > self.volume_length or entry.size > self.volume_length - offset:
            raise IsoError(f"extent outside ISO: {entry.name}")

    def _entry(self, raw: bytes) -> Entry:
        if len(raw) < 34 or raw[0] < 34 or raw[0] > len(raw):
            raise IsoError("invalid ISO directory record")
        raw = raw[:raw[0]]
        length = raw[32]
        if length == 0 or 33 + length > len(raw):
            raise IsoError("invalid ISO file name")
        name_bytes = raw[33:33 + length]
        if name_bytes in (b"\x00", b"\x01"):
            name = "." if name_bytes == b"\x00" else ".."
        else:
            try:
                name = name_bytes.decode("ascii")
            except UnicodeDecodeError as exc:
                raise IsoError("non-ASCII ISO file names are unsupported") from exc
            name = re.sub(r";[0-9]+$", "", name)
            if (name in ("", ".", "..") or "/" in name or "\\" in name
                    or ":" in name or any(ord(c) < 32 or ord(c) == 127 for c in name)):
                raise IsoError(f"unsafe ISO file name: {name!r}")
        if raw[25] & 0x80:
            raise IsoError("multi-extent ISO files are unsupported")
        entry = Entry(name, _both32(raw[2:10]), _both32(raw[10:18]), bool(raw[25] & 2))
        self._check_bounds(entry)
        return entry

    def root_files(self) -> dict[str, Entry]:
        if self.root.size > 16 * 1024 * 1024:
            raise IsoError("ISO root directory is too large")
        data = self._read_at(self.root.extent * SECTOR, self.root.size)
        files: dict[str, Entry] = {}
        pos = 0
        while pos < len(data):
            size = data[pos]
            if size == 0:
                pos = (pos // SECTOR + 1) * SECTOR
                continue
            if pos % SECTOR + size > SECTOR or pos + size > len(data):
                raise IsoError("ISO record crosses a sector boundary")
            entry = self._entry(data[pos:pos + size])
            pos += size
            if entry.name in (".", ".."):
                continue
            key = entry.name.upper()
            if key in files:
                raise IsoError(f"duplicate ISO file name: {entry.name}")
            files[key] = entry
        return files

    def read_small(self, entry: Entry, limit: int) -> bytes:
        if entry.directory or entry.size > limit:
            raise IsoError(f"invalid or oversized ISO file: {entry.name}")
        return self._read_at(entry.extent * SECTOR, entry.size)

    def copy(self, entry: Entry, destination: Path) -> str:
        if entry.directory or entry.size > MAX_EXTRACTED_FILE:
            raise IsoError(f"invalid or oversized ISO file: {entry.name}")
        digest = hashlib.sha256()
        self.file.seek(entry.extent * SECTOR)
        remaining = entry.size
        with destination.open("xb") as target:
            while remaining:
                chunk = self.file.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise IsoError("ISO image was truncated during extraction")
                target.write(chunk)
                digest.update(chunk)
                remaining -= len(chunk)
        return digest.hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _selected_files(iso: IsoImage) -> dict[str, Entry]:
    root = iso.root_files()
    config = root.get("SYSTEM.CNF")
    if config is None:
        raise IsoError("SYSTEM.CNF is missing from the ISO root")
    text = iso.read_small(config, 4096).decode("ascii", "replace")
    if not re.search(r"(?im)^\s*BOOT2\s*=\s*cdrom0:\\SCUS_973\.99;1\s*$", text):
        raise IsoError("SYSTEM.CNF does not identify revision SCUS_973.99")
    elf = root.get(ELF_NAME)
    if elf is None or elf.directory:
        raise IsoError("SCUS_973.99 is missing from the ISO root")
    irx = {name: entry for name, entry in root.items() if name.endswith(".IRX") and not entry.directory}
    for required in ("SMPD_IOP.IRX", "989NOMID.IRX", "LIBSD.IRX"):
        if required not in irx:
            raise IsoError(f"{required} is missing from the ISO root")
    selected = {ELF_NAME: elf, **{name.lower(): entry for name, entry in irx.items()}}
    if sum(entry.size for entry in selected.values()) > MAX_EXTRACTED_TOTAL:
        raise IsoError("required files exceed the extraction size limit")
    return selected


def _cache_root() -> Path:
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".cache"
    if not base.is_absolute():
        raise IsoError("XDG_CACHE_HOME must be an absolute path")
    return base / "gow-one-recomp" / "SCUS-97399"


def _valid_cache(folder: Path, fingerprint: dict[str, object], names: set[str]) -> bool:
    try:
        if folder.is_symlink() or not folder.is_dir():
            return False
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("version") != CACHE_VERSION or manifest.get("source") != fingerprint:
            return False
        hashes = manifest.get("sha256")
        if not isinstance(hashes, dict) or set(hashes) != names:
            return False
        for name, expected in hashes.items():
            dest = folder / (name if name == ELF_NAME else f"IOP_MOD/{name}")
            if dest.is_symlink() or not dest.is_file() or _sha256(dest) != expected:
                return False
        return hashes[ELF_NAME] == ELF_SHA256
    except (OSError, ValueError, TypeError, KeyError):
        return False


def prepare(iso_path: Path, cache_root: Path | None = None) -> Path:
    iso_path = iso_path.expanduser().resolve(strict=True)
    if not iso_path.is_file():
        raise IsoError("the selected path is not an ISO file")
    source_stat = iso_path.stat()
    fingerprint: dict[str, object] = {
        "path": str(iso_path), "size": source_stat.st_size, "mtime_ns": source_stat.st_mtime_ns,
        "device": source_stat.st_dev, "inode": source_stat.st_ino,
    }
    key = hashlib.sha256(json.dumps(fingerprint, sort_keys=True).encode()).hexdigest()[:24]
    root = cache_root or _cache_root()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.is_symlink():
        raise IsoError("the cache directory cannot be a symbolic link")
    os.chmod(root, 0o700)
    folder = root / key
    with IsoImage(iso_path) as iso:
        selected = _selected_files(iso)
        names = set(selected)
        if _valid_cache(folder, fingerprint, names):
            return folder / ELF_NAME
        if folder.exists() or folder.is_symlink():
            shutil.rmtree(folder) if folder.is_dir() and not folder.is_symlink() else folder.unlink()
        staging = Path(tempfile.mkdtemp(prefix=".preparando-", dir=root))
        try:
            (staging / "IOP_MOD").mkdir(mode=0o700)
            hashes = {}
            for name, entry in selected.items():
                target = staging / (name if name == ELF_NAME else f"IOP_MOD/{name}")
                hashes[name] = iso.copy(entry, target)
            if hashes[ELF_NAME] != ELF_SHA256:
                raise IsoError("SCUS_973.99 SHA-256 does not match the supported revision")
            end_stat = iso_path.stat()
            if (end_stat.st_size, end_stat.st_mtime_ns, end_stat.st_dev, end_stat.st_ino) != (
                source_stat.st_size, source_stat.st_mtime_ns, source_stat.st_dev, source_stat.st_ino
            ):
                raise IsoError("the ISO changed during extraction")
            (staging / "manifest.json").write_text(json.dumps({
                "version": CACHE_VERSION, "source": fingerprint, "sha256": hashes,
            }, sort_keys=True), encoding="utf-8")
            try:
                staging.rename(folder)
            except OSError:
                # Another instance finished preparing the same ISO.
                if not _valid_cache(folder, fingerprint, names):
                    raise IsoError("another instance left an incomplete cache; try again")
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    return folder / ELF_NAME


def _choose_iso() -> Path:
    try:
        import tkinter
        from tkinter import filedialog

        window = tkinter.Tk()
        window.withdraw()
        try:
            selected = filedialog.askopenfilename(title="Choose a God of War SCUS-97399 ISO",
                                                   filetypes=[("ISO image", "*.iso"), ("All files", "*")])
        finally:
            window.destroy()
        if selected:
            return Path(selected)
    except Exception:  # tkinter or the graphical display may be unavailable.
        pass
    if sys.stdin.isatty():
        selected = input("ISO path: ").strip()
        if selected:
            return Path(selected)
    raise IsoError("specify the ISO with --iso (no graphical picker is available)")


def _runner_path(explicit: Path | None) -> Path:
    if explicit is not None:
        runner = explicit
    elif os.environ.get("GOW_RUNNER"):
        runner = Path(os.environ["GOW_RUNNER"])
    else:
        runner = Path(__file__).resolve().parents[2] / "bin" / "ps2EntryRunner"
    runner = runner.expanduser().resolve()
    if not runner.is_file() or not os.access(runner, os.X_OK):
        raise IsoError(f"native runner not found or not executable: {runner}; use --runner")
    return runner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start God of War SCUS-97399 from your own ISO")
    parser.add_argument("--iso", type=Path, help="original ISO image (opens a picker if omitted)")
    parser.add_argument("--runner", type=Path, help="prebuilt native ps2EntryRunner")
    parser.add_argument("--prepare-only", action="store_true", help="validate and prepare the cache without launching")
    args = parser.parse_args(argv)
    try:
        iso_path = args.iso or _choose_iso()
        runner = None if args.prepare_only else _runner_path(args.runner)
        elf = prepare(iso_path)
        if args.prepare_only:
            print(f"Prepared: {elf}")
            return 0
        environment = os.environ.copy()
        environment["GOW_ISO"] = str(iso_path.expanduser().resolve())
        assert runner is not None
        return subprocess.call([str(runner), str(elf)], cwd=elf.parent, env=environment)
    except (IsoError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
