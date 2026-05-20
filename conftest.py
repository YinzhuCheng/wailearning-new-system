from __future__ import annotations

import os
from pathlib import Path


if os.name == "nt":
    import _pytest.pathlib as pytest_pathlib
    import _pytest.tmpdir as pytest_tmpdir

    _orig_iterdir = Path.iterdir
    _orig_getbasetemp = pytest_tmpdir.TempPathFactory.getbasetemp

    def _safe_iterdir(self: Path):
        try:
            yield from _orig_iterdir(self)
        except PermissionError:
            normalized = str(self).replace("\\", "/").lower()
            if "/.pytest_tmp/" in normalized or normalized.endswith("/pytest-of-bloom"):
                return
            raise

    Path.iterdir = _safe_iterdir
    pytest_pathlib._force_symlink = lambda *args, **kwargs: None

    def _safe_make_numbered_dir(root: Path, prefix: str, mode: int = 0o700) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        for _ in range(10):
            max_existing = max(map(pytest_pathlib.parse_num, pytest_pathlib.find_suffixes(root, prefix)), default=-1)
            new_number = max_existing + 1
            new_path = root.joinpath(f"{prefix}{new_number}")
            try:
                new_path.mkdir()
            except FileExistsError:
                continue
            return new_path
        raise OSError(f"could not create numbered dir with prefix {prefix} in {root} after 10 tries")

    pytest_pathlib.make_numbered_dir = _safe_make_numbered_dir
    pytest_tmpdir.make_numbered_dir = _safe_make_numbered_dir

    _repo_root = Path(__file__).resolve().parent
    _temp_root = _repo_root / ".pytest_tmp" / f"temproot-{os.getpid()}"
    _basetemp = _repo_root / ".pytest_tmp" / f"basetemp-{os.getpid()}"
    _temp_root.mkdir(parents=True, exist_ok=True)
    _basetemp.mkdir(parents=True, exist_ok=True)

    def _safe_getbasetemp(self):
        if getattr(self, "_basetemp", None) is None:
            self._basetemp = _basetemp.resolve()
        return self._basetemp

    pytest_tmpdir.TempPathFactory.getbasetemp = _safe_getbasetemp

    os.environ["PYTEST_DEBUG_TEMPROOT"] = str(_temp_root)
    os.environ["TMP"] = str(_temp_root)
    os.environ["TEMP"] = str(_temp_root)
