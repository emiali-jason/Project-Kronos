"""Offline exact-source transport qualification; no new authority or acquisition."""
from dataclasses import asdict
from datetime import datetime
from hashlib import sha256
from io import BytesIO
import json
import shutil
import stat
import struct
from zipfile import ZIP_BZIP2, ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

import pytest

from kronos.instrument.option_series import DEFAULT_OPTION_ROOT, OptionAuthorityError
from kronos.market.option_expiry import DEFAULT_EXPIRY_ROOT, read_dst_source
from kronos.theta.target_authority import OwnerOptionAuthority


SHA = "25cf0d761b6383d096622600fa27dbce89c986437a06e753375eaf7b105ccdf6"
LOGICAL = "sources/nist-dst-2026.html"
PACKAGE = "sources/nist-dst-2026.zip"


@pytest.fixture
def estate(tmp_path):
    instrument, market = tmp_path / "instrument", tmp_path / "market"
    shutil.copytree(DEFAULT_OPTION_ROOT, instrument)
    shutil.copytree(DEFAULT_EXPIRY_ROOT, market)
    source = json.loads((market / "2026.2.0.json").read_bytes())["supporting_source"]
    return instrument, market, source


def package(members, *, compression=ZIP_DEFLATED, symlink=False):
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        for name, raw in members:
            info = ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = compression
            info.external_attr = (stat.S_IFLNK | 0o777 if symlink else stat.S_IFREG | 0o644) << 16
            archive.writestr(info, raw)
    return output.getvalue()


def inventory(root):
    return {str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def test_retained_original_exact_and_read_has_no_side_effect(estate):
    _, root, source = estate
    before = inventory(root)
    original = read_dst_source(root, source)
    assert sha256(original).hexdigest() == source["sha256"] == SHA
    assert len(original) == 90882
    with ZipFile(root / PACKAGE) as archive:
        assert archive.namelist() == ["nist-dst-2026.html"]
        assert archive.read("nist-dst-2026.html") == original
    assert not (root / LOGICAL).exists()
    assert inventory(root) == before


@pytest.mark.parametrize("current", ["current.json", "current-2026.1.0.json"])
def test_raw_and_packaged_layouts_have_identical_authority_and_targets(estate, current):
    instrument, root, source = estate
    packaged = OwnerOptionAuthority(instrument_root=instrument, market_root=root,
                                   current_filename=current)
    original = read_dst_source(root, source)
    (root / LOGICAL).write_bytes(original)
    (root / PACKAGE).unlink()
    raw = OwnerOptionAuthority(instrument_root=instrument, market_root=root,
                              current_filename=current)
    assert packaged.descriptor == raw.descriptor
    assert asdict(packaged.instrument) == asdict(raw.instrument)
    assert asdict(packaged.market) == asdict(raw.market)
    at = datetime.fromisoformat("2026-10-12T12:00:00+05:30")
    for subject in ("GOLDM", "SILVERM", "COPPER", "CRUDEOIL", "NATURALGAS"):
        assert packaged.resolve(subject, at) == raw.resolve(subject, at)


def test_valid_raw_layout_does_not_depend_on_package(estate):
    _, root, source = estate
    original = read_dst_source(root, source)
    (root / LOGICAL).write_bytes(original)
    (root / PACKAGE).write_bytes(b"invalid container")
    assert read_dst_source(root, source) == original


@pytest.mark.parametrize("kind", ["corrupt", "symlink", "directory"])
def test_existing_invalid_raw_artifact_is_not_masked(estate, kind):
    _, root, source = estate
    original = read_dst_source(root, source)
    path = root / LOGICAL
    if kind == "corrupt":
        path.write_bytes(original + b"altered")
    elif kind == "symlink":
        target = root / "foreign.html"
        target.write_bytes(original)
        path.symlink_to(target)
    else:
        path.mkdir()
    with pytest.raises(OptionAuthorityError):
        read_dst_source(root, source)


@pytest.mark.parametrize("kind", ["missing", "symlink", "directory", "invalid", "truncated", "changed"])
def test_invalid_packaged_source_fails_closed(estate, kind):
    instrument, root, source = estate
    owner = OwnerOptionAuthority(instrument_root=instrument, market_root=root)
    path = root / PACKAGE
    raw = path.read_bytes()
    path.unlink()
    if kind == "symlink":
        target = root / "foreign.zip"
        target.write_bytes(raw)
        path.symlink_to(target)
    elif kind == "directory":
        path.mkdir()
    elif kind == "invalid":
        path.write_bytes(b"not a ZIP: sensitive arbitrary exception text")
    elif kind == "truncated":
        path.write_bytes(raw[:-12])
    elif kind == "changed":
        path.write_bytes(package([("nist-dst-2026.html", b"changed source")]))
    with pytest.raises(OptionAuthorityError) as failure:
        read_dst_source(root, source)
    assert str(failure.value).startswith("OPTION_AUTHORITY_")
    assert "sensitive" not in str(failure.value)
    with pytest.raises(OptionAuthorityError):
        owner.eligible("GOLDM", datetime.fromisoformat("2026-10-12T12:00:00+05:30"))


@pytest.mark.parametrize("kind", ["extra", "wrong", "traversal", "symlink", "bzip2", "empty", "oversized", "encrypted", "bad_crc"])
def test_untrusted_archive_structure_is_not_authority(estate, kind):
    _, root, source = estate
    original = read_dst_source(root, source)
    members = [("nist-dst-2026.html", original)]
    if kind == "extra":
        members.append(("unrelated.txt", b"extra"))
    elif kind == "wrong":
        members[0] = ("foreign.html", original)
    elif kind == "traversal":
        members[0] = ("../nist-dst-2026.html", original)
    elif kind == "empty":
        members = []
    raw = bytearray(package(members, compression=ZIP_BZIP2 if kind == "bzip2" else ZIP_STORED,
                            symlink=kind == "symlink"))
    if kind in {"oversized", "encrypted", "bad_crc"}:
        central = raw.index(b"PK\x01\x02")
        if kind == "oversized":
            struct.pack_into("<I", raw, 22, 20 * 1024 * 1024 + 1)
            struct.pack_into("<I", raw, central + 24, 20 * 1024 * 1024 + 1)
        elif kind == "encrypted":
            struct.pack_into("<H", raw, 6, 1)
            struct.pack_into("<H", raw, central + 8, 1)
        else:
            raw[30 + len("nist-dst-2026.html")] ^= 1
    (root / PACKAGE).write_bytes(raw)
    with pytest.raises(OptionAuthorityError, match="SOURCE_INVALID"):
        read_dst_source(root, source)
    assert not (root / LOGICAL).exists()


@pytest.mark.parametrize("key,value", [
    ("filename", "../escape.html"), ("filename", "/escape.html"),
    ("filename", "sources/foreign.html"), ("sha256", "0" * 64),
])
def test_logical_pin_and_path_remain_mandatory(estate, key, value):
    _, root, source = estate
    source[key] = value
    with pytest.raises(OptionAuthorityError):
        read_dst_source(root, source)
