"""Install bundled BSP demo sources into a stable Codex data directory."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import time
import uuid
import zipfile


LOCK_TIMEOUT_SECONDS = 120
STALE_LOCK_SECONDS = 600


def _load_manifest(data_dir: Path) -> dict[str, object]:
    return json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))


def _matching_release(manifest: dict[str, object], version: str) -> dict[str, object] | None:
    requested = version.split(".")
    release = ".".join(requested[:3])
    candidates = []
    for item in manifest.get("bsp_releases", []):
        demo_version = str(item.get("demo_version", ""))
        if demo_version == version or demo_version == release or demo_version.startswith(f"{release}."):
            candidates.append(item)
    return max(candidates, key=lambda item: str(item["demo_version"]), default=None)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_member_path(member: zipfile.ZipInfo, destination: Path) -> Path:
    if "\\" in member.filename:
        raise ValueError(f"Unsafe path separator in BSP demo archive: {member.filename!r}")
    name = PurePosixPath(member.filename)
    if name.is_absolute() or ".." in name.parts or not name.parts:
        raise ValueError(f"Unsafe path in BSP demo archive: {member.filename!r}")
    if any(":" in part for part in name.parts) or member.filename.startswith(("\\", "//")):
        raise ValueError(f"Unsafe path in BSP demo archive: {member.filename!r}")
    mode = member.external_attr >> 16
    if stat.S_ISLNK(mode):
        raise ValueError(f"Symbolic links are not allowed in BSP demo archive: {member.filename!r}")
    return destination.joinpath(*name.parts)


def _extract_archive(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            target = _safe_member_path(member, destination)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.open(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def _acquire_lock(lock_path: Path) -> int:
    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    while True:
        try:
            return os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                if time.time() - lock_path.stat().st_mtime > STALE_LOCK_SECONDS:
                    lock_path.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for BSP demo installation lock: {lock_path}")
            time.sleep(0.2)


def ensure_demo_sources(data_dir: Path, cache_root: Path, version: str) -> tuple[str, Path]:
    """Return demo version and stable extracted src directory."""

    release = _matching_release(_load_manifest(data_dir), version)
    if release is None:
        raise FileNotFoundError(f"No bundled demo configuration for BSP {version}")

    demo_version = str(release["demo_version"])
    archive = data_dir / str(release["demo_archive"])
    expected_sha256 = str(release["demo_sha256"])
    version_root = cache_root / demo_version
    source_root = version_root / "src"
    marker = version_root / ".package.json"
    expected_marker = {"demo_version": demo_version, "sha256": expected_sha256}

    if source_root.is_dir() and marker.is_file():
        try:
            if json.loads(marker.read_text(encoding="utf-8")) == expected_marker:
                return demo_version, source_root
        except (OSError, ValueError):
            pass

    cache_root.mkdir(parents=True, exist_ok=True)
    lock_path = cache_root / f".{demo_version}.lock"
    lock_fd = _acquire_lock(lock_path)
    try:
        if source_root.is_dir() and marker.is_file():
            try:
                if json.loads(marker.read_text(encoding="utf-8")) == expected_marker:
                    return demo_version, source_root
            except (OSError, ValueError):
                pass

        if not archive.is_file():
            raise FileNotFoundError(f"Bundled BSP demo archive is missing: {archive}")
        actual_sha256 = _sha256(archive)
        if actual_sha256 != expected_sha256:
            raise ValueError(
                f"BSP demo archive checksum mismatch: expected {expected_sha256}, got {actual_sha256}"
            )

        staging = cache_root / f".{demo_version}.staging-{os.getpid()}-{uuid.uuid4().hex}"
        backup = cache_root / f".{demo_version}.backup-{uuid.uuid4().hex}"
        try:
            staging.mkdir(parents=True)
            _extract_archive(archive, staging)
            staged_source = staging / "src"
            if not staged_source.is_dir() or not any(staged_source.iterdir()):
                raise ValueError("BSP demo archive does not contain a non-empty src directory")
            (staging / ".package.json").write_text(
                json.dumps(expected_marker, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            if version_root.exists():
                version_root.replace(backup)
            try:
                staging.replace(version_root)
            except Exception:
                if backup.exists() and not version_root.exists():
                    backup.replace(version_root)
                raise
            if backup.exists():
                shutil.rmtree(backup)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        return demo_version, source_root
    finally:
        os.close(lock_fd)
        lock_path.unlink(missing_ok=True)
