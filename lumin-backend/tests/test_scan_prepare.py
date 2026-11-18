"""A recording is read once and shared between the steps of a scan (app/scan_fp.prepare), without changing what they see."""
import subprocess

import numpy as np
import pytest

from app import scan_fp


@pytest.fixture()
def clip(tmp_path):
    p = tmp_path / "c.webm"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x568:r=15", "-f", "lavfi", "-i", "sine=f=440",
         "-t", "4", "-c:v", "libvpx", "-c:a", "libopus", str(p)],
        check=True,
    )
    yield str(p)
    scan_fp.forget_prepared(p)


def test_the_recording_is_decoded_once_for_every_step(clip, monkeypatch):
    calls = {"frames": 0}
    real = scan_fp.read_frames

    def counting(*a, **k):
        calls["frames"] += 1
        return real(*a, **k)

    monkeypatch.setattr(scan_fp, "read_frames", counting)
    scan_fp.detect_rect(clip)
    scan_fp.extract_query(clip)
    scan_fp.extract_query(clip, crop=(0, 100, 0, 100))
    assert calls["frames"] == 1


def test_a_step_cannot_change_what_the_next_one_sees(clip):
    length, (h, t), frames, times = scan_fp.prepare(clip)
    frames.clear()
    times.append(99.0)
    h[:] = 0
    length2, (h2, t2), frames2, times2 = scan_fp.prepare(clip)
    assert length2 == length and len(frames2) > 0 and 99.0 not in times2
    assert h2.size == 0 or h2.any()


def test_forgetting_releases_it_and_a_changed_file_is_read_again(clip, monkeypatch):
    scan_fp.prepare(clip)
    scan_fp.forget_prepared(clip)
    assert not scan_fp._PREP
    n = len(scan_fp.prepare(clip)[2])
    assert n > 0
