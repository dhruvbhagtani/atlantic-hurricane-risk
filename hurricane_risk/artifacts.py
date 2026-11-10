"""Publish completed runs without overwriting previous experiments."""
from contextlib import contextmanager
import hashlib
import shutil
import tempfile
from pathlib import Path


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@contextmanager
def output_directory(destination):
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError(f"Output already exists: {destination}. Choose a new --out directory.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        yield temporary
        # mkdir reserves the final name; competing runs cannot replace each other.
        destination.mkdir()
        try:
            temporary.rename(destination)
        except BaseException:
            destination.rmdir()
            raise
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def output_hashes(out):
    return {str(p.relative_to(out)): sha256(p) for p in sorted(Path(out).rglob("*"))
            if p.is_file() and p.name != "manifest.json"}
