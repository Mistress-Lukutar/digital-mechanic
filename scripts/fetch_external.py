'''
File:   fetch_external.py
Brief:  Deployment fetch: password-protected bundle of eval sets and
        the manual prompt block.
Author: Mistress-Lukutar
Date:   2026-11-27
Version: v0.1.0

The RAG eval question sets (RAG_EVAL_DIR) and the manual-specific prompt
block (PROMPT_MANUAL_FILE) quote the copyrighted factory manuals, so they
never enter the repository. They travel as ONE password-protected archive
on the same shared storage as the manual PDFs: EXTERNAL_CONTENT_URL in the
gitignored .env points at the archive (or at a folder holding it), and
EXTERNAL_CONTENT_PASSWORD unlocks it. Both secrets stay local, exactly
like MANUALS_DOWNLOAD_URL — the link and the password are never committed.

The archive is an AES-encrypted zip (built with pyzipper). Reading it
needs the optional dependency:

    pip install pyzipper

Usage (from the repository root):

    python scripts/fetch_external.py              # download + unpack
    python scripts/fetch_external.py --list       # show contents only
    python scripts/fetch_external.py --from FILE  # unpack a local archive
    python scripts/fetch_external.py --allow-plain  # allow unencrypted zip

Archive layout (one wrapping top-level folder is tolerated):

    rag-eval/golden.jsonl ...      -> RAG_EVAL_DIR
    prompt-manual/system-manual.md -> directory of PROMPT_MANUAL_FILE

Both destinations must live OUTSIDE the repository tree (the committed
prompt skeleton and the guard tests assume it), so the script refuses
in-repo targets. The downloaded archive itself is staged under
EXTERNAL_CONTENT_DIR (default data/external/, gitignored).
'''

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import fetch_manuals  # noqa: E402  (sibling script, same directory)

# Bucket (top-level archive folder) -> what it fills. rag-eval is
# mandatory (eval runs are pointless without it); the prompt block is
# optional because the prompt builder works without it (skeleton note).
BUCKET_RAG_EVAL = "rag-eval"
BUCKET_PROMPT_MANUAL = "prompt-manual"

STAGING_NAME = "external-content.zip"
MAX_UNPACKED_BYTES = 512 * 1024 * 1024


def env_value(name: str, values: dict[str, str], default: str = "") -> str:
    '''Read a variable from the environment, falling back to repo .env.

    Args:
        name: Variable name (e.g. EXTERNAL_CONTENT_URL).
        values: Parsed .env mapping (fetch_manuals.read_env_file).
        default: Value when neither source has the variable.

    Returns:
        The effective value (environment wins over .env).
    '''
    import os

    value = os.environ.get(name)
    if value:
        return value
    return values.get(name, default).strip()


def staging_dir(values: dict[str, str]) -> Path:
    '''Return the staging directory for the downloaded archive.

    Args:
        values: Parsed .env mapping.

    Returns:
        EXTERNAL_CONTENT_DIR when set, else <repo>/data/external (the
        archive is encrypted, and the directory is gitignored).
    '''
    configured = env_value("EXTERNAL_CONTENT_DIR", values)
    if configured:
        path = Path(configured)
    else:
        path = REPO_ROOT / "data" / "external"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _latest_zip(items: list[dict[str, Any]]) -> dict[str, Any]:
    '''Pick the newest zip item when a folder holds several versions.

    Args:
        items: Public-folder file items ending in .zip.

    Returns:
        The item with the latest "modified" timestamp.
    '''
    if len(items) == 1:
        return items[0]
    print(f"WARNING: {len(items)} archives in the folder, taking the newest")
    return max(items, key=lambda item: str(item.get("modified", "")))


def download_archive(values: dict[str, str]) -> Path:
    '''Download the bundle from the shared storage link.

    The link may point at the archive file itself or at a folder that
    contains it; in the folder case the newest *.zip wins.

    Args:
        values: Parsed .env mapping.

    Returns:
        Path of the downloaded archive in the staging directory.
    '''
    url = env_value("EXTERNAL_CONTENT_URL", values)
    if not url:
        raise SystemExit(
            "ERROR: EXTERNAL_CONTENT_URL is not set — point it at the "
            "public archive (or the folder holding it) in the gitignored "
            ".env, or use --from for a local file"
        )
    meta = fetch_manuals.api_get({"public_key": url})
    if meta.get("type") == "file":
        item: dict[str, Any] = meta
    else:
        zips = [
            entry
            for entry in fetch_manuals.walk_public_folder(url)
            if str(entry.get("name", "")).lower().endswith(".zip")
        ]
        if not zips:
            raise SystemExit("ERROR: no .zip archive found at the link")
        item = _latest_zip(zips)
    name = str(item.get("name", STAGING_NAME))
    size = int(item.get("size") or 0)
    print(f"Fetching {name} ({fetch_manuals.fmt_mb(size)}) ...")
    href = fetch_manuals.download_href(url, str(item["path"]))
    target = staging_dir(values) / STAGING_NAME
    fetch_manuals.download_to(href, target, size)
    return target


def _zip_reader():
    '''Return the zip class able to read AES-encrypted archives.

    pyzipper (AES + ZipCrypto + plain) is preferred; stdlib zipfile is
    the fallback and only handles ZipCrypto/plain archives.

    Returns:
        A ZipFile-compatible class.

    Raises:
        SystemExit: When pyzipper is missing (hint included) — kept
            separate from the read-time error so --list works on plain
            archives without pyzipper too.
    '''
    try:
        import pyzipper

        return pyzipper.AESZipFile
    except ImportError:
        import zipfile

        return zipfile.ZipFile


def _open_archive(path: Path, password: str, allow_plain: bool):
    '''Open the archive, enforcing the encryption policy.

    Args:
        path: Archive file path.
        password: EXTERNAL_CONTENT_PASSWORD value (may be empty).
        allow_plain: When True, an unencrypted archive is accepted.

    Returns:
        An open zip file object positioned for reading.

    Raises:
        SystemExit: On missing password for an encrypted archive, on a
            plain archive without --allow-plain, or on a bad password.
    '''
    reader = _zip_reader()
    with reader(path) as probe:
        encrypted = any(info.flag_bits & 0x1 for info in probe.infolist())
    if encrypted and not password:
        raise SystemExit(
            "ERROR: the archive is encrypted but EXTERNAL_CONTENT_PASSWORD "
            "is not set (gitignored .env)"
        )
    if not encrypted and not allow_plain:
        raise SystemExit(
            "ERROR: the archive is NOT encrypted — the bundle quotes the "
            "manuals, pass --allow-plain only if you really mean it"
        )
    try:
        archive = reader(path)
        if password:
            archive.setpassword(password.encode("utf-8"))
        return archive
    except Exception as exc:  # noqa: BLE001 - report any open problem
        raise SystemExit(f"ERROR: cannot open {path.name}: {exc}") from exc


def bucket_targets(values: dict[str, str]) -> dict[str, Path]:
    '''Resolve where each archive bucket unpacks to.

    Args:
        values: Parsed .env mapping.

    Returns:
        Mapping of bucket name ("rag-eval", "prompt-manual") to its
        destination directory. prompt-manual is skipped with a warning
        when PROMPT_MANUAL_FILE is not configured.

    Raises:
        SystemExit: When RAG_EVAL_DIR is missing or a target sits inside
            the repository tree.
    '''
    targets: dict[str, Path] = {}
    eval_dir = env_value("RAG_EVAL_DIR", values)
    if not eval_dir:
        raise SystemExit(
            "ERROR: RAG_EVAL_DIR is not set — the rag-eval bucket has "
            "nowhere to unpack (set it to a directory OUTSIDE the repo)"
        )
    targets[BUCKET_RAG_EVAL] = Path(eval_dir)
    prompt_file = env_value("PROMPT_MANUAL_FILE", values)
    if prompt_file:
        targets[BUCKET_PROMPT_MANUAL] = Path(prompt_file).parent
    else:
        print(
            "WARNING: PROMPT_MANUAL_FILE is not set — the prompt-manual "
            "bucket is skipped (the prompt runs without the block)"
        )
    repo_root = REPO_ROOT.resolve()
    for bucket, target in targets.items():
        resolved = target.resolve()
        if resolved == repo_root or resolved.is_relative_to(repo_root):
            raise SystemExit(
                f"ERROR: {bucket} target {resolved} is inside the "
                "repository tree — quoted manual content must stay "
                "outside it (see .env.example)"
            )
    return targets


def _strip_root(names: list[str]) -> list[str]:
    '''Strip one wrapping top-level folder from archive paths.

    Args:
        names: File entry names inside the archive (forward slashes).

    Returns:
        Entry names relative to the bucket level.
    '''
    first = {name.split("/", 1)[0] for name in names if "/" in name}
    if len(names) > 1 and len(first) == 1 and "" not in first:
        root = first.pop()
        stripped = [name.split("/", 1)[1] for name in names]
        if all(stripped):
            print(f"Archive root: {root}/ (stripped)")
            return stripped
    return names


def _safe_dest(bucket_dir: Path, rel: str) -> Path:
    '''Resolve one archive entry to a destination path, zip-slip-safe.

    Args:
        bucket_dir: The bucket's destination directory.
        rel: Entry path relative to the bucket (forward slashes).

    Returns:
        The absolute destination path.

    Raises:
        SystemExit: When the entry escapes the bucket directory (path
            traversal, absolute path or Windows drive component).
    '''
    if rel.startswith("/") or "\\" in rel or ":" in rel:
        raise SystemExit(f"ERROR: unsafe archive entry: {rel!r}")
    parts = rel.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise SystemExit(f"ERROR: unsafe archive entry: {rel!r}")
    dest = (bucket_dir / rel).resolve()
    if not dest.is_relative_to(bucket_dir.resolve()):
        raise SystemExit(f"ERROR: entry escapes the target: {rel!r}")
    return dest


def unpack(archive_path: Path, values: dict[str, str], allow_plain: bool) -> int:
    '''Unpack the bundle into the configured destinations.

    Args:
        archive_path: Archive file path.
        values: Parsed .env mapping.
        allow_plain: When True, an unencrypted archive is accepted.

    Returns:
        Number of files written.
    '''
    password = env_value("EXTERNAL_CONTENT_PASSWORD", values)
    targets = bucket_targets(values)
    archive = _open_archive(archive_path, password, allow_plain)
    with archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        total = sum(info.file_size for info in infos)
        if total > MAX_UNPACKED_BYTES:
            raise SystemExit(
                f"ERROR: archive unpacks to {fetch_manuals.fmt_mb(total)}, "
                f"over the {fetch_manuals.fmt_mb(MAX_UNPACKED_BYTES)} cap"
            )
        originals = [info.filename for info in infos]
        stripped = _strip_root(originals)
        by_original = dict(zip(originals, infos, strict=True))
        written = 0
        for original, rel in zip(originals, stripped, strict=True):
            bucket, _, sub = rel.partition("/")
            if not sub:
                raise SystemExit(
                    f"ERROR: stray top-level entry {rel!r} — expected "
                    f"{BUCKET_RAG_EVAL}/ or {BUCKET_PROMPT_MANUAL}/"
                )
            bucket_dir = targets.get(bucket)
            if bucket_dir is None:
                raise SystemExit(f"ERROR: unexpected bucket {bucket!r}")
            dest = _safe_dest(bucket_dir, sub)
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                dest.write_bytes(archive.read(by_original[original]))
            except Exception as exc:  # noqa: BLE001 - usually a bad password
                dest.unlink(missing_ok=True)
                raise SystemExit(
                    f"ERROR: cannot decrypt {rel!r} — check "
                    "EXTERNAL_CONTENT_PASSWORD"
                ) from exc
            written += 1
        for bucket, target in targets.items():
            print(f"{bucket}/ -> {target.resolve()}")
    print(f"Unpacked {written} file(s) from {archive_path.name}")
    return written


def list_contents(archive_path: Path, password: str, allow_plain: bool) -> None:
    '''Print the archive listing with sizes.

    Args:
        archive_path: Archive file path.
        password: EXTERNAL_CONTENT_PASSWORD value (may be empty).
        allow_plain: When True, an unencrypted archive is accepted.
    '''
    archive = _open_archive(archive_path, password, allow_plain)
    with archive:
        for info in archive.infolist():
            kind = "dir " if info.is_dir() else "file"
            print(f"{kind}  {fetch_manuals.fmt_mb(info.file_size):>8}  "
                  f"{info.filename}")


def main(argv: list[str] | None = None) -> None:
    '''Command-line entry point.

    Args:
        argv: Argument list (defaults to sys.argv[1:]).
    '''
    parser = argparse.ArgumentParser(
        description=(
            "Fetch and unpack the password-protected bundle of RAG eval "
            "sets and the manual prompt block (secrets in gitignored .env)"
        )
    )
    parser.add_argument(
        "--from",
        dest="from_file",
        type=Path,
        default=None,
        help="unpack a local archive instead of downloading",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="list the archive contents and exit",
    )
    parser.add_argument(
        "--allow-plain",
        action="store_true",
        help="accept an unencrypted archive (content quotes the manuals)",
    )
    args = parser.parse_args(argv)

    values = fetch_manuals.read_env_file(REPO_ROOT)
    if args.from_file is not None:
        if not args.from_file.is_file():
            raise SystemExit(f"ERROR: no such file: {args.from_file}")
        archive_path = args.from_file
    else:
        archive_path = download_archive(values)

    password = env_value("EXTERNAL_CONTENT_PASSWORD", values)
    if args.list:
        list_contents(archive_path, password, args.allow_plain)
        return
    unpack(archive_path, values, args.allow_plain)


if __name__ == "__main__":
    main()
