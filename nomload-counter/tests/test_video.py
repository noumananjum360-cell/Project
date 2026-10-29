import time

from nomload.core.video import SourceSpec, VideoSource, mask_url, rtsp_url


def test_offline_for_never_crashes_during_state_change():
    """Regression: the reader thread clears offline_since while the bay thread reads it."""
    src = VideoSource(SourceSpec("file", "missing.mp4"), "t")
    src.online = False
    src.offline_since = None          # the moment between the two assignments in the reader thread
    assert src.offline_for() == 0.0
    src.offline_since = time.time() - 5
    assert 4.5 < src.offline_for() < 6
    src.online = True
    assert src.offline_for() == 0.0


def test_rtsp_helper_and_masking():
    u = rtsp_url("Hikvision", "192.168.1.64", "admin", "p@ss word", substream=True)
    assert u == "rtsp://admin:p%40ss%20word@192.168.1.64:554/Streaming/Channels/102"
    assert "p%40ss" not in mask_url(u) and "****" in mask_url(u)
    assert rtsp_url("Dahua", "10.0.0.2", "admin", "x").endswith("/cam/realmonitor?channel=1&subtype=0")


def test_file_source_lockstep_delivers_every_frame(tmp_path):
    import cv2
    import numpy as np
    p = tmp_path / "v.avi"
    vw = cv2.VideoWriter(str(p), cv2.VideoWriter_fourcc(*"MJPG"), 15, (64, 48))
    for i in range(30):
        vw.write(np.full((48, 64, 3), i * 8, np.uint8))
    vw.release()
    src = VideoSource(SourceSpec("file", str(p), loop=False, realtime=False), "t")
    src.start()
    got, last = 0, -1
    t0 = time.time()
    while not src.ended and time.time() - t0 < 20:
        r = src.read(last, 0.5)
        if r:
            last = r[0]
            got += 1
            time.sleep(0.01)  # slow consumer: lockstep must not drop frames
    src.stop()
    assert got == 30
