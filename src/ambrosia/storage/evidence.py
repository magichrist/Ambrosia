"""Filesystem evidence store.

Evidence files are stored under generated IDs in a controlled application
data directory. Caller-supplied paths are never used for storage layout: the
database keeps only metadata and the generated relative path.
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import os


class EvidenceStore:
    """Content-addressed evidence file store.

    Files are written to ``<root>/<id[:2]>/<id>`` so directories stay small.
    ``relative_path`` (``<id[:2]>/<id>``) is what gets persisted in the
    database.
    """

    def __init__(self, root_dir: str | os.PathLike[str] | None = None) -> None:
        self.root_dir = Path(root_dir) if root_dir is not None else Path.home() / ".ambrosia" / "evidence"
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def store_file(
        self,
        source_path: str | os.PathLike[str],
        *,
        generated_id: str | None = None,
    ) -> dict[str, Any]:
        """Copy ``source_path`` into the store under a generated ID.

        Returns a dict with ``generated_id``, ``relative_path``, ``filename``,
        ``content_hash`` (SHA-256), and ``size``.
        """
        data = Path(source_path).read_bytes()
        content_hash = hashlib.sha256(data).hexdigest()
        generated_id = generated_id or str(uuid.uuid4())
        subdir = self.root_dir / generated_id[:2]
        subdir.mkdir(parents=True, exist_ok=True)
        stored_path = subdir / generated_id
        stored_path.write_bytes(data)
        relative_path = f"{generated_id[:2]}/{generated_id}"
        return {
            "generated_id": generated_id,
            "relative_path": relative_path,
            "filename": Path(source_path).name,
            "content_hash": content_hash,
            "size": len(data),
        }

    def path_for(self, relative_path: str) -> Path:
        """Absolute filesystem path for a stored relative path."""
        return self.root_dir / relative_path

    def verify(self, relative_path: str, expected_hash: str) -> bool:
        """Verify a stored file's SHA-256 against an expected value."""
        stored_path = self.path_for(relative_path)
        if not stored_path.is_file():
            return False
        digest = hashlib.sha256(stored_path.read_bytes()).hexdigest()
        return digest == expected_hash
