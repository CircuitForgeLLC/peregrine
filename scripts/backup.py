"""Config backup / restore / teleport for Peregrine.

Creates a portable zip of all gitignored configs + optionally the staging DB.
Intended for: machine migrations, Docker volume transfers, and safe wizard testing.
Supports both the Peregrine Docker instance and the legacy /devl/job-seeker install.

Cloud mode notes
----------------
In cloud mode (CLOUD_MODE=true), the staging DB is SQLCipher-encrypted.
Pass the per-user ``db_key`` to ``create_backup()`` to have it transparently
decrypt the DB before archiving — producing a portable, plain SQLite file
that works with any local Docker install.

Pass the same ``db_key`` to ``restore_backup()`` and it will re-encrypt the
plain DB on its way in, so the cloud app can open it normally.

Usage (CLI):
    conda run -n job-seeker python scripts/backup.py --create backup.zip
    conda run -n job-seeker python scripts/backup.py --create backup.zip --no-db
    conda run -n job-seeker python scripts/backup.py --create backup.zip --base-dir /devl/job-seeker
    conda run -n job-seeker python scripts/backup.py --restore backup.zip
    conda run -n job-seeker python scripts/backup.py --list   backup.zip

Usage (programmatic — called from Settings UI):
    from scripts.backup import create_backup, restore_backup, list_backup_contents
    zip_bytes = create_backup(base_dir, include_db=True)
    info      = list_backup_contents(zip_bytes)
    result    = restore_backup(zip_bytes, base_dir, include_db=True)
"""
from __future__ import annotations

import io
import json
import os
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Files included in every backup (relative to repo root)
# ---------------------------------------------------------------------------

# Gitignored config files that hold secrets / personal data
_SECRET_CONFIGS = [
    "config/notion.yaml",
    "config/tokens.yaml",
    "config/email.yaml",
    "config/adzuna.yaml",
    "config/craigslist.yaml",
    "config/user.yaml",
    "config/plain_text_resume.yaml",
    "config/license.json",
    "config/user.yaml.working",
]

# Gitignored integration configs (glob pattern — each matching file is added)
_INTEGRATION_CONFIG_GLOB = "config/integrations/*.yaml"

# Non-secret committed configs worth preserving for portability
# (also present in the legacy /devl/job-seeker instance)
_EXTRA_CONFIGS = [
    "config/llm.yaml",
    "config/search_profiles.yaml",
    "config/resume_keywords.yaml",  # personal keyword list — present in both instances
    "config/skills_suggestions.yaml",
    "config/blocklist.yaml",
    "config/server.yaml",           # deployment config (base URL path, port) — Peregrine only
]

# Candidate DB paths (first one that exists wins)
_DB_CANDIDATES = ["data/staging.db", "staging.db"]

_MANIFEST_NAME = "backup-manifest.json"


# ---------------------------------------------------------------------------
# SQLCipher helpers (cloud mode only — only called when db_key is set)
# ---------------------------------------------------------------------------

def _decrypt_db_to_bytes(db_path: Path, db_key: str) -> bytes:
    """Open a SQLCipher-encrypted DB and return plain SQLite bytes.

    Uses SQLCipher's ATTACH + sqlcipher_export() to produce a portable
    unencrypted copy. Only called in cloud mode (db_key non-empty).
    pysqlcipher3 is available in the Docker image (Dockerfile installs
    libsqlcipher-dev); never called in local-mode tests.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        from pysqlcipher3 import dbapi2 as _sqlcipher  # type: ignore[import]
        conn = _sqlcipher.connect(str(db_path))
        conn.execute(f"PRAGMA key='{db_key}'")
        conn.execute(f"ATTACH DATABASE '{tmp_path}' AS plaintext KEY ''")
        conn.execute("SELECT sqlcipher_export('plaintext')")
        conn.execute("DETACH DATABASE plaintext")
        conn.close()
        return Path(tmp_path).read_bytes()
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def _encrypt_db_from_bytes(plain_bytes: bytes, dest_path: Path, db_key: str) -> None:
    """Write plain SQLite bytes as a SQLCipher-encrypted DB at dest_path.

    Used on restore in cloud mode to convert a portable plain backup into
    the per-user encrypted format the app expects.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp.write(plain_bytes)
        tmp_path = tmp.name
    try:
        from pysqlcipher3 import dbapi2 as _sqlcipher  # type: ignore[import]
        # Open the plain DB (empty key = no encryption in SQLCipher)
        conn = _sqlcipher.connect(tmp_path)
        conn.execute("PRAGMA key=''")
        # Attach the encrypted destination and export there
        conn.execute(f"ATTACH DATABASE '{dest_path}' AS encrypted KEY '{db_key}'")
        conn.execute("SELECT sqlcipher_export('encrypted')")
        conn.execute("DETACH DATABASE encrypted")
        conn.close()
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Source detection
# ---------------------------------------------------------------------------

def _detect_source_label(base_dir: Path) -> str:
    """Return a human-readable label for the instance being backed up.

    Uses the directory name — stable as long as the repo root isn't renamed,
    which is the normal case for both the Docker install (peregrine/) and the
    legacy Conda install (job-seeker/).

    Args:
        base_dir: The root directory being backed up.

    Returns:
        A short identifier string, e.g. "peregrine" or "job-seeker".
    """
    return base_dir.name


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_backup(
    base_dir: Path,
    include_db: bool = True,
    source_label: str | None = None,
    db_key: str = "",
) -> bytes:
    """Return a zip archive as raw bytes.

    Args:
        base_dir:     Repo root (parent of config/ and staging.db).
        include_db:   If True, include staging.db in the archive.
        source_label: Human-readable instance name stored in the manifest
                      (e.g. "peregrine", "job-seeker"). Auto-detected if None.
        db_key:       SQLCipher key for the DB (cloud mode). When set, the DB
                      is decrypted before archiving so the backup is portable
                      to any local Docker install.
    """
    buf = io.BytesIO()
    included: list[str] = []

    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # Gitignored secret configs
        for rel in _SECRET_CONFIGS:
            p = base_dir / rel
            if p.exists():
                zf.write(p, rel)
                included.append(rel)

        # Integration configs (glob)
        for p in sorted((base_dir).glob(_INTEGRATION_CONFIG_GLOB)):
            rel = str(p.relative_to(base_dir))
            zf.write(p, rel)
            included.append(rel)

        # Extra non-secret configs
        for rel in _EXTRA_CONFIGS:
            p = base_dir / rel
            if p.exists():
                zf.write(p, rel)
                included.append(rel)

        # Staging DB
        if include_db:
            for candidate in _DB_CANDIDATES:
                p = base_dir / candidate
                if p.exists():
                    if db_key:
                        # Cloud mode: decrypt to plain SQLite before archiving
                        plain_bytes = _decrypt_db_to_bytes(p, db_key)
                        zf.writestr(candidate, plain_bytes)
                    else:
                        zf.write(p, candidate)
                    included.append(candidate)
                    break

        # Manifest
        manifest = {
            "created_at": datetime.now().isoformat(),
            "source": source_label or _detect_source_label(base_dir),
            "source_path": str(base_dir.resolve()),
            "peregrine_version": "1.0",
            "files": included,
            "includes_db": include_db and any(f.endswith(".db") for f in included),
        }
        zf.writestr(_MANIFEST_NAME, json.dumps(manifest, indent=2))

    return buf.getvalue()


def list_backup_contents(zip_bytes: bytes) -> dict:
    """Return manifest + file list from a backup zip (no extraction)."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = [n for n in zf.namelist() if n != _MANIFEST_NAME]
        manifest: dict = {}
        if _MANIFEST_NAME in zf.namelist():
            manifest = json.loads(zf.read(_MANIFEST_NAME))
        sizes = {info.filename: info.file_size for info in zf.infolist()}
    return {
        "manifest": manifest,
        "files": names,
        "sizes": sizes,
        "total_bytes": sum(sizes[n] for n in names if n in sizes),
    }


def restore_backup(
    zip_bytes: bytes,
    base_dir: Path,
    include_db: bool = True,
    overwrite: bool = True,
    db_key: str = "",
) -> dict[str, list[str]]:
    """Extract a backup zip into base_dir.

    Args:
        zip_bytes:  Raw bytes of the backup zip.
        base_dir:   Repo root to restore into.
        include_db: If False, skip any .db files.
        overwrite:  If False, skip files that already exist.
        db_key:     SQLCipher key (cloud mode). When set, any .db file in the
                    zip (plain SQLite) is re-encrypted on the way in so the
                    cloud app can open it normally.

    Returns:
        {"restored": [...], "skipped": [...]}
    """
    restored: list[str] = []
    skipped: list[str] = []

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            if name == _MANIFEST_NAME:
                continue
            if not include_db and name.endswith(".db"):
                skipped.append(name)
                continue
            dest = base_dir / name
            if dest.exists() and not overwrite:
                skipped.append(name)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            raw = zf.read(name)
            if db_key and name.endswith(".db"):
                # Cloud mode: the zip contains plain SQLite — re-encrypt on restore
                _encrypt_db_from_bytes(raw, dest, db_key)
            else:
                dest.write_bytes(raw)
            restored.append(name)

    return {"restored": restored, "skipped": skipped}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Peregrine config backup / restore / teleport")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--create", metavar="OUT.zip", help="Create a backup zip")
    group.add_argument("--restore", metavar="IN.zip", help="Restore from a backup zip")
    group.add_argument("--list", metavar="IN.zip", help="List contents of a backup zip")
    parser.add_argument("--no-db", action="store_true", help="Exclude staging.db (--create/--restore)")
    parser.add_argument("--no-overwrite", action="store_true",
                        help="Skip files that already exist (--restore)")
    parser.add_argument(
        "--base-dir", metavar="PATH",
        help="Root of the instance to back up/restore (default: this repo root). "
             "Use /devl/job-seeker to target the legacy Conda install.",
    )
    args = parser.parse_args()

    base_dir = Path(args.base_dir).resolve() if args.base_dir else Path(__file__).parent.parent

    if args.create:
        out = Path(args.create)
        data = create_backup(base_dir, include_db=not args.no_db)
        out.write_bytes(data)
        info = list_backup_contents(data)
        m = info["manifest"]
        print(f"Backup created: {out}  ({len(data):,} bytes)")
        print(f"  Source: {m.get('source', '?')}  ({base_dir})")
        print(f"  {len(info['files'])} files archived:")
        for name in info["files"]:
            size = info["sizes"].get(name, 0)
            print(f"    {name}  ({size:,} bytes)")

    elif args.restore:
        in_path = Path(args.restore)
        if not in_path.exists():
            print(f"ERROR: {in_path} not found", file=sys.stderr)
            sys.exit(1)
        data = in_path.read_bytes()
        result = restore_backup(data, base_dir,
                                include_db=not args.no_db,
                                overwrite=not args.no_overwrite)
        print(f"Restored {len(result['restored'])} files:")
        for name in result["restored"]:
            print(f"  ✓ {name}")
        if result["skipped"]:
            print(f"Skipped {len(result['skipped'])} files:")
            for name in result["skipped"]:
                print(f"  - {name}")

    elif args.list:
        in_path = Path(args.list)
        if not in_path.exists():
            print(f"ERROR: {in_path} not found", file=sys.stderr)
            sys.exit(1)
        data = in_path.read_bytes()
        info = list_backup_contents(data)
        m = info["manifest"]
        if m:
            print(f"Created:  {m.get('created_at', 'unknown')}")
            print(f"Source:   {m.get('source', '?')}  ({m.get('source_path', '?')})")
            print(f"Has DB:   {m.get('includes_db', '?')}")
        print(f"\n{len(info['files'])} files  ({info['total_bytes']:,} bytes uncompressed):")
        for name in info["files"]:
            size = info["sizes"].get(name, 0)
            print(f"  {name}  ({size:,} bytes)")


if __name__ == "__main__":
    main()
