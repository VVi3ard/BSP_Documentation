from pathlib import Path

import pytest

from bsp_docs_mcp.versions import (
    BspVersion,
    VersionDetectionError,
    detect_bsp_version,
    extract_bsp_version,
)


@pytest.mark.parametrize(
    ("raw", "full", "family"),
    [
        ("3.1.11.155", "3.1.11.155", "3.1"),
        ("3_1_11_155", "3.1.11.155", "3.1"),
        ("3.1", "3.1", "3.1"),
    ],
)
def test_normalizes_versions(raw: str, full: str, family: str) -> None:
    version = BspVersion.parse(raw)
    assert version.full == full
    assert version.family == family


def test_rejects_incomplete_or_non_numeric_versions() -> None:
    with pytest.raises(ValueError):
        BspVersion.parse("3")
    with pytest.raises(ValueError):
        BspVersion.parse("3.1.preview")


def test_extracts_nearest_version_before_bsp_marker() -> None:
    content = (
        '{6,0,"2.0.1.7","ДругаяБиблиотека",'
        'c05f,"3.1.11.155","Фирма ""1С""",'
        '"БиблиотекаСтандартныхПодсистем",7900}'
    )
    assert extract_bsp_version(content).full == "3.1.11.155"


def test_detection_reads_legacy_parent_configurations_bin(tmp_path: Path) -> None:
    path = tmp_path / "ParentConfigurations.bin"
    path.write_bytes(
        '{6,0,"3.1.11.155","БиблиотекаСтандартныхПодсистем"}'.encode("utf-8")
    )
    assert detect_bsp_version(path).family == "3.1"


def test_detection_reads_distribution_support_xml(tmp_path: Path) -> None:
    path = tmp_path / "Configuration.distr"
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<distributionSupport:DistributionSupport xmlns:distributionSupport="http://g5.1c.ru/v8/dt/distribution/model" version="6" updateAvailable="true">
  <parentConfigurationInfos configRelease="3.1.11.155" configName="БиблиотекаСтандартныхПодсистем"/>
</distributionSupport:DistributionSupport>
""",
        encoding="utf-8",
    )

    assert detect_bsp_version(path).full == "3.1.11.155"


def test_missing_bsp_marker_is_clear_error() -> None:
    with pytest.raises(VersionDetectionError, match="БиблиотекаСтандартныхПодсистем"):
        extract_bsp_version('{6,0,"3.1.11.155","ДругаяБиблиотека"}')
