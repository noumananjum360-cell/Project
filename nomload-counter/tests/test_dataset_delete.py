import cv2
import numpy as np
import pytest

from nomload.training.dataset import Dataset


@pytest.fixture
def ds(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMLOAD_HOME", str(tmp_path))
    d = Dataset.create("site")
    img = np.zeros((40, 60, 3), np.uint8)
    for name in ("my_phone_video_000000", "my_phone_video_000015", "bay1_cam_000030", "synthetic_77_00001"):
        cv2.imwrite(str(d.images / f"{name}.jpg"), img)
        d.write_labels(d.images / f"{name}.jpg", [(0, 5, 5, 30, 30)], 60, 40)
    return d


def test_sources_grouped_by_video(ds):
    assert ds.sources() == {"bay1_cam": 1, "my_phone_video": 2, "synthetic_77": 1}


def test_delete_frames_of_one_video(ds):
    assert ds.delete_source("my_phone_video") == 2
    assert "my_phone_video" not in ds.sources()
    assert not list(ds.labels.glob("my_phone_video*"))       # labels removed too
    assert ds.stats()["images"] == 2


def test_delete_selected_images_and_clear_labels(ds):
    img = ds.images / "bay1_cam_000030.jpg"
    ds.clear_labels(img)
    assert not ds.is_labeled(img)
    assert ds.delete_images([img]) == 1
    assert not img.exists()


def test_delete_dataset(ds):
    ds.delete()
    assert not ds.root.exists()
    assert all(d.name != "site" for d in Dataset.list_all())


def test_model_delete_guards(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMLOAD_HOME", str(tmp_path))
    from nomload.config import user_models_dir
    from nomload.training.trainer import delete_model
    m1, m2 = user_models_dir() / "detector_a.onnx", user_models_dir() / "detector_b.onnx"
    for m in (m1, m2):
        m.write_bytes(b"x")
        m.with_suffix(".json").write_text("{}")
    with pytest.raises(ValueError):
        delete_model(m1, m1)                     # active model is kept
    with pytest.raises(ValueError):
        delete_model(tmp_path / "starter_detector.onnx", m1)   # not a user model
    delete_model(m2, m1)
    assert not m2.exists() and not m2.with_suffix(".json").exists()
