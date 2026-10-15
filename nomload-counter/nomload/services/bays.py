"""Loading bays and their cameras."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import cv2
import numpy as np

from nomload.core.geometry import CountGeometry
from nomload.core.video import SourceSpec
from nomload.data import crypto
from nomload.data.db import Database
from nomload.services.context import User, audit


@dataclass
class Camera:
    id: int
    bay_id: int
    name: str
    role: str
    source: SourceSpec
    geometry: CountGeometry
    reference: np.ndarray | None
    active: bool


@dataclass
class Bay:
    id: int
    name: str
    active: bool
    auto_session: bool
    config: dict
    cameras: list[Camera] = field(default_factory=list)

    @property
    def count_camera(self) -> Camera | None:
        return next((c for c in self.cameras if c.role == "count" and c.active), None)

    @property
    def plate_camera(self) -> Camera | None:
        return next((c for c in self.cameras if c.role == "plate" and c.active), None)


class BayService:
    def __init__(self, db: Database):
        self.db = db

    def _cam(self, r) -> Camera:
        src = json.loads(crypto.decrypt(r["source"]) or "{}")
        ref = None
        if r["reference"]:
            ref = cv2.imdecode(np.frombuffer(r["reference"], np.uint8), cv2.IMREAD_COLOR)
        return Camera(r["id"], r["bay_id"], r["name"], r["role"], SourceSpec.from_dict(src),
                      CountGeometry.from_dict(json.loads(r["geometry"] or "{}")), ref, bool(r["active"]))

    def list(self, active_only=False) -> list[Bay]:
        bays = []
        for r in self.db.q("SELECT * FROM bays" + (" WHERE active=1" if active_only else "") + " ORDER BY id"):
            b = Bay(r["id"], r["name"], bool(r["active"]), bool(r["auto_session"]), json.loads(r["config"] or "{}"))
            b.cameras = [self._cam(c) for c in self.db.q("SELECT * FROM cameras WHERE bay_id=? ORDER BY id", (b.id,))]
            bays.append(b)
        return bays

    def get(self, bay_id: int) -> Bay | None:
        return next((b for b in self.list() if b.id == bay_id), None)

    def count(self) -> int:
        return self.db.scalar("SELECT COUNT(*) FROM bays WHERE active=1") or 0

    def save_bay(self, actor: User, name: str, auto_session: bool = False, bay_id: int | None = None,
                 active: bool = True) -> int:
        if bay_id:
            self.db.execute("UPDATE bays SET name=?, auto_session=?, active=? WHERE id=?",
                            (name, int(auto_session), int(active), bay_id))
            audit(self.db, actor, "bay_updated", "bay", bay_id, {"name": name, "active": active})
            return bay_id
        bid = self.db.execute("INSERT INTO bays(name, auto_session) VALUES (?, ?)", (name, int(auto_session)))
        audit(self.db, actor, "bay_created", "bay", bid, {"name": name})
        return bid

    def save_camera(self, actor: User, bay_id: int, name: str, role: str, source: SourceSpec,
                    geometry: CountGeometry | None = None, cam_id: int | None = None, active: bool = True) -> int:
        src = crypto.encrypt(json.dumps(source.to_dict()))
        geo = json.dumps((geometry or CountGeometry()).to_dict())
        if cam_id:
            self.db.execute("UPDATE cameras SET bay_id=?, name=?, role=?, source=?, geometry=?, active=? WHERE id=?",
                            (bay_id, name, role, src, geo, int(active), cam_id))
            audit(self.db, actor, "camera_updated", "camera", cam_id, {"name": name, "role": role, "kind": source.kind})
            return cam_id
        cid = self.db.execute("INSERT INTO cameras(bay_id, name, role, source, geometry, active) VALUES (?,?,?,?,?,?)",
                              (bay_id, name, role, src, geo, int(active)))
        audit(self.db, actor, "camera_created", "camera", cid, {"name": name, "role": role, "kind": source.kind})
        return cid

    def save_calibration(self, actor: User, cam_id: int, geometry: CountGeometry, reference: np.ndarray | None):
        blob = None
        if reference is not None:
            ok, enc = cv2.imencode(".jpg", reference, [cv2.IMWRITE_JPEG_QUALITY, 90])
            blob = enc.tobytes() if ok else None
        self.db.execute("UPDATE cameras SET geometry=?, reference=COALESCE(?, reference) WHERE id=?",
                        (json.dumps(geometry.to_dict()), blob, cam_id))
        audit(self.db, actor, "camera_calibrated", "camera", cam_id, geometry.to_dict())

    def delete_camera(self, actor: User, cam_id: int):
        self.db.execute("UPDATE cameras SET active=0 WHERE id=?", (cam_id,))
        audit(self.db, actor, "camera_disabled", "camera", cam_id)
