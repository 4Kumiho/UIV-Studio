# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.

"""SQLite persistence for recordings (*.uivr) and runs (*.uivx).

Workspace layout:
    <workspace>/recordings/<name>/recording.uivr
    <workspace>/runs/<name>__<timestamp>/run.uivx   (+ video.mp4)
"""

import json
import re
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from uiv_studio import __version__
from uiv_studio.core.models import (MatchInfo, RecordingInfo, RunInfo, RunStep,
                                    Step, Target)

RECORDING_FILE = "recording.uivr"
RUN_FILE = "run.uivx"
VIDEO_FILE = "video.mp4"

_REC_SCHEMA = """
CREATE TABLE IF NOT EXISTS info (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    name TEXT NOT NULL, created_at TEXT NOT NULL,
    screen_w INTEGER NOT NULL, screen_h INTEGER NOT NULL, scale REAL NOT NULL,
    app_version TEXT, description TEXT
);
CREATE TABLE IF NOT EXISTS step (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idx INTEGER NOT NULL, action TEXT NOT NULL,
    screenshot BLOB, modifiers TEXT, text TEXT, enter_after INTEGER, key TEXT,
    scroll_dx INTEGER, scroll_dy INTEGER, wait_s REAL, testcase TEXT, note TEXT
);
CREATE TABLE IF NOT EXISTS target (
    step_id INTEGER NOT NULL REFERENCES step(id) ON DELETE CASCADE,
    role TEXT NOT NULL,              -- 'main' | 'drop'
    meta TEXT NOT NULL, template BLOB, embedding BLOB,
    PRIMARY KEY (step_id, role)
);
"""

_RUN_SCHEMA = """
CREATE TABLE IF NOT EXISTS info (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    recording_name TEXT, recording_path TEXT, started_at TEXT, ended_at TEXT,
    result TEXT, error TEXT, screen_w INTEGER, screen_h INTEGER, scale REAL, video TEXT
);
CREATE TABLE IF NOT EXISTS run_step (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idx INTEGER NOT NULL, action TEXT, status TEXT, started_s REAL, duration_s REAL,
    match TEXT, match_crop BLOB, drop_match TEXT, drop_crop BLOB, error TEXT, testcase TEXT
);
"""


def safe_name(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().strip(".")
    return cleaned or "untitled"


def _connect(path: Path, schema: str) -> sqlite3.Connection:
    con = sqlite3.connect(str(path), check_same_thread=False)
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    con.executescript(schema)
    return con


# ============================================================ Recording


class Recording:
    """A recording file. Thread-safe enough for our use: one writer at a time."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.con = _connect(self.path, _REC_SCHEMA)

    # ---------- lifecycle
    @classmethod
    def create(cls, workspace: Path, name: str, screen_w: int, screen_h: int, scale: float,
               description: str = "") -> "Recording":
        folder = workspace / "recordings" / safe_name(name)
        if folder.exists():
            raise FileExistsError(str(folder))
        folder.mkdir(parents=True)
        rec = cls(folder / RECORDING_FILE)
        with rec.con:
            rec.con.execute(
                "INSERT INTO info VALUES (1, ?, ?, ?, ?, ?, ?, ?)",
                (name, datetime.now().isoformat(timespec="seconds"), screen_w, screen_h, scale,
                 __version__, description),
            )
        return rec

    def close(self):
        self.con.close()

    @property
    def folder(self) -> Path:
        return self.path.parent

    # ---------- info
    def info(self) -> RecordingInfo:
        r = self.con.execute(
            "SELECT name, created_at, screen_w, screen_h, scale, app_version, description FROM info"
        ).fetchone()
        return RecordingInfo(*r)

    def update_info(self, **fields):
        allowed = {"name", "description"}
        for k, v in fields.items():
            if k in allowed:
                with self.con:
                    self.con.execute(f"UPDATE info SET {k} = ? WHERE id = 1", (v,))

    # ---------- steps
    def _row_to_step(self, row, targets) -> Step:
        (sid, idx, action, shot, mods, text, enter, key, sdx, sdy, wait_s, tc, note) = row
        return Step(
            id=sid, idx=idx, action=action, screenshot=shot or b"",
            modifiers=json.loads(mods or "[]"), text=text or "", enter_after=bool(enter),
            key=key or "", scroll_dx=sdx or 0, scroll_dy=sdy or 0, wait_s=wait_s or 0.0,
            testcase=tc or "", note=note or "",
            target=targets.get((sid, "main")), drop=targets.get((sid, "drop")),
        )

    def _targets(self, where: str = "", args=()) -> dict:
        out = {}
        for step_id, role, meta, tpl, emb in self.con.execute(
                f"SELECT step_id, role, meta, template, embedding FROM target {where}", args):
            m = json.loads(meta)
            out[(step_id, role)] = Target(template=tpl or b"", embedding=emb or b"", **m)
        return out

    _STEP_COLS = ("id, idx, action, screenshot, modifiers, text, enter_after, key, "
                  "scroll_dx, scroll_dy, wait_s, testcase, note")

    def steps(self, with_screens: bool = True) -> list[Step]:
        cols = self._STEP_COLS if with_screens else self._STEP_COLS.replace("screenshot", "NULL")
        rows = self.con.execute(f"SELECT {cols} FROM step ORDER BY idx").fetchall()
        targets = self._targets()
        return [self._row_to_step(r, targets) for r in rows]

    def step(self, step_id: int) -> Step | None:
        r = self.con.execute(f"SELECT {self._STEP_COLS} FROM step WHERE id = ?", (step_id,)).fetchone()
        if not r:
            return None
        return self._row_to_step(r, self._targets("WHERE step_id = ?", (step_id,)))

    def step_count(self) -> int:
        return self.con.execute("SELECT COUNT(*) FROM step").fetchone()[0]

    def _write_targets(self, step: Step):
        self.con.execute("DELETE FROM target WHERE step_id = ?", (step.id,))
        for role, t in (("main", step.target), ("drop", step.drop)):
            if t is not None:
                self.con.execute(
                    "INSERT INTO target VALUES (?, ?, ?, ?, ?)",
                    (step.id, role, json.dumps(t.meta()), t.template, t.embedding),
                )

    def add_step(self, step: Step, index: int | None = None) -> Step:
        """Append (or insert at 1-based `index`) a step; returns it with id/idx set."""
        with self.con:
            count = self.step_count()
            if index is None or index > count:
                step.idx = count + 1
            else:
                step.idx = max(1, index)
                self.con.execute("UPDATE step SET idx = idx + 1 WHERE idx >= ?", (step.idx,))
            cur = self.con.execute(
                "INSERT INTO step (idx, action, screenshot, modifiers, text, enter_after, key, "
                "scroll_dx, scroll_dy, wait_s, testcase, note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (step.idx, step.action, step.screenshot, json.dumps(step.modifiers), step.text,
                 int(step.enter_after), step.key, step.scroll_dx, step.scroll_dy, step.wait_s,
                 step.testcase, step.note),
            )
            step.id = cur.lastrowid
            self._write_targets(step)
        return step

    def update_step(self, step: Step):
        with self.con:
            self.con.execute(
                "UPDATE step SET action=?, screenshot=?, modifiers=?, text=?, enter_after=?, key=?, "
                "scroll_dx=?, scroll_dy=?, wait_s=?, testcase=?, note=? WHERE id=?",
                (step.action, step.screenshot, json.dumps(step.modifiers), step.text,
                 int(step.enter_after), step.key, step.scroll_dx, step.scroll_dy, step.wait_s,
                 step.testcase, step.note, step.id),
            )
            self._write_targets(step)

    def delete_step(self, step_id: int):
        with self.con:
            self.con.execute("DELETE FROM step WHERE id = ?", (step_id,))
            self._renumber()

    def move_step(self, step_id: int, new_index: int):
        """Move a step to 1-based position `new_index`."""
        ids = [r[0] for r in self.con.execute("SELECT id FROM step ORDER BY idx")]
        if step_id not in ids:
            return
        ids.remove(step_id)
        ids.insert(max(0, min(new_index - 1, len(ids))), step_id)
        with self.con:
            for i, sid in enumerate(ids, start=1):
                self.con.execute("UPDATE step SET idx = ? WHERE id = ?", (i, sid))

    def _renumber(self):
        ids = [r[0] for r in self.con.execute("SELECT id FROM step ORDER BY idx")]
        for i, sid in enumerate(ids, start=1):
            self.con.execute("UPDATE step SET idx = ? WHERE id = ?", (i, sid))

    def append_from(self, other: "Recording"):
        """Append all steps of another recording (the old 'aggregate' feature)."""
        for s in other.steps():
            s.id = None
            self.add_step(s)


def list_recordings(workspace: Path) -> list[dict]:
    out = []
    root = workspace / "recordings"
    if not root.is_dir():
        return out
    for folder in sorted(root.iterdir()):
        f = folder / RECORDING_FILE
        if not f.is_file():
            continue
        try:
            with closing(sqlite3.connect(str(f))) as con:
                info = con.execute("SELECT name, created_at, screen_w, screen_h, scale, description FROM info").fetchone()
                count = con.execute("SELECT COUNT(*) FROM step").fetchone()[0]
            out.append({
                "path": f, "name": info[0], "created_at": info[1],
                "screen": f"{info[2]}×{info[3]} @ {round(info[4] * 100)}%",
                "description": info[5] or "", "steps": count,
                "modified": f.stat().st_mtime,
            })
        except Exception:
            continue
    out.sort(key=lambda r: r["modified"], reverse=True)
    return out


def delete_recording(path: Path):
    shutil.rmtree(Path(path).parent, ignore_errors=True)


def duplicate_recording(path: Path, new_name: str) -> Path:
    src = Path(path).parent
    dst = src.parent / safe_name(new_name)
    if dst.exists():
        raise FileExistsError(str(dst))
    dst.mkdir()
    with closing(sqlite3.connect(str(path))) as con_src, closing(sqlite3.connect(str(dst / RECORDING_FILE))) as con_dst:
        con_src.backup(con_dst)
        con_dst.execute("UPDATE info SET name = ? WHERE id = 1", (new_name,))
        con_dst.commit()
    return dst / RECORDING_FILE


# ============================================================ Run


class Run:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.con = _connect(self.path, _RUN_SCHEMA)

    @classmethod
    def create(cls, workspace: Path, info: RunInfo) -> "Run":
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = workspace / "runs" / f"{safe_name(info.recording_name)}__{stamp}"
        folder, n = base, 1
        while folder.exists():
            n += 1
            folder = base.with_name(f"{base.name}_{n}")
        folder.mkdir(parents=True)
        run = cls(folder / RUN_FILE)
        with run.con:
            run.con.execute(
                "INSERT INTO info VALUES (1,?,?,?,?,?,?,?,?,?,?)",
                (info.recording_name, info.recording_path, info.started_at, info.ended_at,
                 info.result, info.error, info.screen_w, info.screen_h, info.scale, info.video),
            )
        return run

    @property
    def folder(self) -> Path:
        return self.path.parent

    def close(self):
        self.con.close()

    def info(self) -> RunInfo:
        r = self.con.execute(
            "SELECT recording_name, recording_path, started_at, ended_at, result, error, "
            "screen_w, screen_h, scale, video FROM info").fetchone()
        return RunInfo(*r)

    def finish(self, result: str, error: str = "", video: str = ""):
        with self.con:
            self.con.execute(
                "UPDATE info SET ended_at=?, result=?, error=?, video=? WHERE id=1",
                (datetime.now().isoformat(timespec="seconds"), result, error, video),
            )

    def add_step(self, rs: RunStep):
        m, d = rs.match, rs.drop_match
        with self.con:
            cur = self.con.execute(
                "INSERT INTO run_step (idx, action, status, started_s, duration_s, match, match_crop, "
                "drop_match, drop_crop, error, testcase) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (rs.idx, rs.action, rs.status, rs.started_s, rs.duration_s,
                 json.dumps(m.meta()) if m else None, m.crop if m else None,
                 json.dumps(d.meta()) if d else None, d.crop if d else None, rs.error, rs.testcase),
            )
            rs.id = cur.lastrowid

    def steps(self) -> list[RunStep]:
        out = []
        for (sid, idx, action, status, started, dur, m, mc, d, dc, err, tc) in self.con.execute(
                "SELECT id, idx, action, status, started_s, duration_s, match, match_crop, drop_match, "
                "drop_crop, error, testcase FROM run_step ORDER BY idx, id"):
            match = MatchInfo(crop=mc or b"", **json.loads(m)) if m else None
            drop = MatchInfo(crop=dc or b"", **json.loads(d)) if d else None
            out.append(RunStep(id=sid, idx=idx, action=action, status=status, started_s=started or 0.0,
                               duration_s=dur or 0.0, match=match, drop_match=drop, error=err or "",
                               testcase=tc or ""))
        return out


def list_runs(workspace: Path) -> list[dict]:
    out = []
    root = workspace / "runs"
    if not root.is_dir():
        return out
    for folder in root.iterdir():
        f = folder / RUN_FILE
        if not f.is_file():
            continue
        try:
            with closing(sqlite3.connect(str(f))) as con:
                i = con.execute("SELECT recording_name, started_at, ended_at, result FROM info").fetchone()
                counts = dict(con.execute("SELECT status, COUNT(*) FROM run_step GROUP BY status").fetchall())
            out.append({"path": f, "recording": i[0], "started_at": i[1], "ended_at": i[2] or "",
                        "result": i[3] or "", "counts": counts, "modified": f.stat().st_mtime})
        except Exception:
            continue
    out.sort(key=lambda r: r["started_at"] or "", reverse=True)
    return out


def delete_run(path: Path):
    shutil.rmtree(Path(path).parent, ignore_errors=True)
