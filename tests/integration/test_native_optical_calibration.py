"""Host checks for the finite framebuffer visibility calibration."""

from __future__ import annotations

import importlib.util
import mmap
from pathlib import Path
import shutil
import subprocess

import pytest


_TARGET = Path(__file__).resolve().parents[2] / "target"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"m1lab_test_{name}", _TARGET / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


calibration = _load("native_optical_calibration")
boot = _load("native_boot")


def test_fixed_matrix_decodes_to_only_the_declared_token(tmp_path):
    if shutil.which("magick") is None or shutil.which("zbarimg") is None:
        pytest.skip("host QR image and decoder tools unavailable")
    raw = bytes(0 if pixel == "1" else 255 for row in calibration.MATRIX for pixel in row)
    portable = tmp_path / "symbol.pgm"
    portable.write_bytes(b"P5\n33 33\n255\n" + raw)
    image = tmp_path / "symbol.png"
    subprocess.run(["magick", str(portable), "-scale", "264x264", str(image)], check=True)
    decoded = subprocess.run(
        ["zbarimg", "--quiet", "--raw", str(image)], check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert decoded.stdout == calibration.TOKEN.encode("ascii") + b"\n"


def test_framebuffer_render_uses_checked_format_and_visible_region():
    variable = calibration._VarScreenInfo()
    variable.xres = variable.xres_virtual = 300
    variable.yres = variable.yres_virtual = 300
    variable.bits_per_pixel = 32
    variable.red.offset, variable.red.length = 16, 8
    variable.green.offset, variable.green.length = 8, 8
    variable.blue.offset, variable.blue.length = 0, 8
    variable.transp.offset, variable.transp.length = 24, 8
    fixed = calibration._FixScreenInfo()
    fixed.visual = 2
    fixed.line_length = 1200
    fixed.smem_len = fixed.line_length * variable.yres
    with mmap.mmap(-1, fixed.smem_len) as framebuffer:
        calibration._render(framebuffer, variable, fixed, scale=8, brightness=180)
        assert framebuffer[0:4] == bytes((180, 180, 180, 255))
        black = (4 * 8 * fixed.line_length) + (4 * 8 * 4)
        assert framebuffer[black:black + 4] == bytes((0, 0, 0, 255))
        beyond = 280 * fixed.line_length + 280 * 4
        assert framebuffer[beyond:beyond + 4] == b"\x00" * 4
        variable.xres = 200
        with pytest.raises(ValueError, match="does not fit"):
            calibration._render(framebuffer, variable, fixed, scale=8, brightness=180)
        variable.xres = 300
        fixed.visual = 4
        with pytest.raises(ValueError, match="unsupported calibration framebuffer memory"):
            calibration._render(framebuffer, variable, fixed, scale=8, brightness=180)


def test_unusual_framebuffer_bitfields_are_rejected():
    variable = calibration._VarScreenInfo()
    variable.bits_per_pixel = 32
    variable.red.offset, variable.red.length = 16, 8
    variable.green.offset, variable.green.length = 8, 8
    variable.blue.offset, variable.blue.length = 0, 8
    variable.transp.offset, variable.transp.length = 24, 8
    assert calibration._pixel(variable, 180) == bytes((180, 180, 180, 255))
    variable.red.msb_right = 1
    with pytest.raises(ValueError, match="color field"):
        calibration._pixel(variable, 180)
    variable.red.msb_right = 0
    variable.transp.offset = 16
    with pytest.raises(ValueError, match="alpha field"):
        calibration._pixel(variable, 180)


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        (b"console=tty0 rdinit=/init\n", False),
        (b"console=tty0 m1lab.optical_calibration=1 rdinit=/init\n", True),
    ],
)
def test_exact_calibration_boot_argument(monkeypatch, tmp_path, arguments, expected):
    cmdline = tmp_path / "cmdline"
    cmdline.write_bytes(arguments)
    original = boot.Path
    monkeypatch.setattr(boot, "Path", lambda value: cmdline if value == "/proc/cmdline" else original(value))
    assert boot._optical_calibration_requested() is expected


def test_duplicate_or_unknown_calibration_boot_argument_fails(monkeypatch, tmp_path):
    cmdline = tmp_path / "cmdline"
    cmdline.write_text("m1lab.optical_calibration=1 m1lab.optical_calibration=1\n")
    original = boot.Path
    monkeypatch.setattr(boot, "Path", lambda value: cmdline if value == "/proc/cmdline" else original(value))
    with pytest.raises(ValueError, match="invalid optical calibration"):
        boot._optical_calibration_requested()


def test_calibration_boot_never_starts_usb_gadget(monkeypatch, tmp_path):
    called = []
    monkeypatch.setattr(boot, "CONSOLE", tmp_path / "absent-tty0")
    monkeypatch.setattr(boot, "_optical_calibration_requested", lambda: True)
    monkeypatch.setattr(boot, "_run_optical_calibration", lambda: called.append("render"))
    monkeypatch.setattr(boot, "_configure_gadget", lambda *_args: called.append("gadget"))
    assert boot.main() == 0
    assert called == ["render"]
