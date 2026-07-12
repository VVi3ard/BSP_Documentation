"""BSP version normalization and project metadata detection."""

from __future__ import annotations

from dataclasses import dataclass
import re
import xml.etree.ElementTree as ET
from pathlib import Path


BSP_MARKER = "БиблиотекаСтандартныхПодсистем"
_VERSION_RE = re.compile(r"^\d+(?:[._]\d+)+$")
_QUOTED_VERSION_RE = re.compile(r'"(\d+(?:\.\d+){1,})"')


class VersionDetectionError(ValueError):
    """Raised when BSP metadata does not contain a usable version."""


@dataclass(frozen=True, slots=True)
class BspVersion:
    """A normalized BSP release and its compatible major/minor family."""

    full: str
    family: str

    @classmethod
    def parse(cls, raw: str) -> "BspVersion":
        normalized = raw.strip().replace("_", ".")
        if not _VERSION_RE.fullmatch(raw.strip()) or normalized.count(".") < 1:
            raise ValueError(
                f"Invalid BSP version {raw!r}; expected at least major.minor, "
                "for example 3.1 or 3.1.11.155"
            )
        parts = normalized.split(".")
        if any(not part.isdigit() for part in parts):
            raise ValueError(f"Invalid BSP version {raw!r}")
        normalized = ".".join(str(int(part)) for part in parts)
        return cls(full=normalized, family=".".join(normalized.split(".")[:2]))


def extract_bsp_version(content: str) -> BspVersion:
    """Extract the closest quoted version preceding the BSP library marker."""

    marker_at = content.find(BSP_MARKER)
    if marker_at < 0:
        raise VersionDetectionError(
            f"Library marker {BSP_MARKER!r} was not found in the source file"
        )
    matches = list(_QUOTED_VERSION_RE.finditer(content, 0, marker_at))
    if not matches:
        raise VersionDetectionError(
            f"No quoted version was found before {BSP_MARKER!r}"
    )
    return BspVersion.parse(matches[-1].group(1))


def _extract_bsp_version_from_distribution_support_xml(content: str) -> BspVersion | None:
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return None

    if not root.tag.endswith("DistributionSupport"):
        return None

    for element in root.iter():
        if element.tag.endswith("parentConfigurationInfos"):
            config_release = element.attrib.get("configRelease")
            if config_release:
                return BspVersion.parse(config_release)
            raise VersionDetectionError(
                "DistributionSupport file has parentConfigurationInfos without configRelease"
            )

    raise VersionDetectionError(
        "DistributionSupport file does not contain parentConfigurationInfos"
    )


def detect_bsp_version(path: str | Path) -> BspVersion:
    """Read a BSP source file and detect its version."""

    source = Path(path)
    raw = source.read_bytes()
    for encoding in ("utf-8-sig", "utf-16", "cp1251"):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        if source.name == "Configuration.distr":
            xml_version = _extract_bsp_version_from_distribution_support_xml(text)
            if xml_version is not None:
                return xml_version
            raise VersionDetectionError(
                f"Configuration.distr at {source} is not valid DistributionSupport XML"
            )
        if source.name == "ParentConfigurations.bin":
            if BSP_MARKER in text:
                return extract_bsp_version(text)
            raise VersionDetectionError(
                f"Library marker {BSP_MARKER!r} was not found in legacy source file {source}"
            )
    raise VersionDetectionError(
        f"Could not detect BSP version in {source}"
    )
