'''
File:   fetch_manuals.py
Brief:  Deployment bootstrap: fetch issued PDFs/DOCX from the shared link.
Author: Demetrius242
Date:   2026-11-27
Version: v0.1.0

The factory manual PDFs (and the case DOCX documents, if wanted) are not
stored in git. At deploy time they are downloaded from a shared storage
link provided through the MANUALS_DOWNLOAD_URL environment variable,
which lives in the gitignored .env — the link itself must never be
committed. Currently a Yandex Disk public folder is supported (public
REST API, standard library only).

Usage (from the repository root):

    python scripts/fetch_manuals.py                 # download pdf + docx
    python scripts/fetch_manuals.py --ext pdf       # only PDFs
    python scripts/fetch_manuals.py --include "536" # name substring filter
    python scripts/fetch_manuals.py --list          # show contents only
    python scripts/fetch_manuals.py --to "D:/docs"  # override target dir

Target directory: --to, else MANUALS_DIR from the environment / .env,
else data/manuals. Files already present with the same size are skipped,
so the script is safe to re-run.

After fetching, recognise and rename the files into the manifest layout
and build the search index:

    python -m rag.setup --from <target dir>
'''

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Iterator

API_BASE = "https://cloud-api.yandex.net/v1/disk/public/resources"
USER_AGENT = {"User-Agent": "digital-mechanic-fetch/0.1"}
DEFAULT_EXTS = ("pdf", "docx")
MAX_DIR_DEPTH = 5
# Some networks break TLS to the storage host intermittently (proxy or
# middlebox resets); retry patiently before giving up.
ATTEMPTS = 5
RETRY_DELAY_SEC = 5.0


def _open(request: urllib.request.Request, *, direct: bool):
    '''Open a URL, optionally bypassing environment proxies.

    Args:
        request: The request to open.
        direct: When True, ignore http_proxy/https_proxy variables (some
            networks break TLS to the storage host through their proxy).

    Returns:
        An open response stream.
    '''
    if direct:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        return opener.open(request, timeout=120)
    return urllib.request.urlopen(request, timeout=120)


def _use_env_proxy() -> bool:
    '''Whether the environment proxy (http_proxy/https_proxy) should be used.

    Off by default: on machines where a local interception proxy (TUN /
    system-proxy mode) is running, a proxied attempt can break even the
    subsequent *direct* sockets of this process, so the proxy route is
    opt-in via MANUALS_FETCH_USE_PROXY=1 for networks where the direct
    route is firewalled.

    Returns:
        True when the caller should go through environment proxies.
    '''
    return os.environ.get("MANUALS_FETCH_USE_PROXY", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _open_with_fallback(request: urllib.request.Request):
    '''Open a request, retrying patiently on the primary route.

    Primary route is DIRECT by default (see :func:`_use_env_proxy`):
    first all direct attempts run; when they all fail, a single proxied
    attempt is made as the last resort (opt-in inverts this order).

    Args:
        request: The request to open.

    Returns:
        An open response stream.

    Raises:
        Exception: The last transport error when every attempt fails.
    '''
    use_proxy = _use_env_proxy()
    last: Exception | None = None
    for _ in range(ATTEMPTS):
        try:
            return _open(request, direct=not use_proxy)
        except Exception as exc:  # noqa: BLE001 - any transport error retries
            last = exc
            time.sleep(RETRY_DELAY_SEC)
    # Last resort: the other route, exactly once (on interception proxies
    # a failed proxied attempt can break later direct sockets, so it is
    # never retried and never run before the primary route).
    try:
        return _open(request, direct=use_proxy)
    except Exception as exc:  # noqa: BLE001 - report the primary error
        raise last if last is not None else exc from exc


def read_env_file(repo_root: Path) -> dict[str, str]:
    '''Parse a simple KEY=VALUE .env (comments, blank lines, quotes).

    Args:
        repo_root: Repository root holding the gitignored .env file.

    Returns:
        Mapping of variable names to values; empty when no .env exists.
    '''
    values: dict[str, str] = {}
    env_path = repo_root / ".env"
    if not env_path.is_file():
        return values
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip("'\"")
        if key.strip():
            values[key.strip()] = value
    return values


def api_get(params: dict[str, str]) -> dict:
    '''Call the Yandex Disk public REST API.

    Args:
        params: Query parameters (public_key, path, offset, limit).

    Returns:
        Parsed JSON response.

    Raises:
        SystemExit: On HTTP or connection errors, with a readable message.
    '''
    url = API_BASE + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers=USER_AGENT)
    try:
        with _open_with_fallback(request) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - report any fetch problem
        raise SystemExit(f"ERROR: shared storage request failed: {exc}") from exc


def walk_public_folder(
    public_key: str, subpath: str = "", depth: int = 0
) -> Iterator[dict]:
    '''Yield every file item of a public folder, recursing into subfolders.

    Args:
        public_key: Public link or hash of the shared folder.
        subpath: Path inside the public folder (empty for the root).
        depth: Current recursion depth (bounded by MAX_DIR_DEPTH).

    Yields:
        Raw API file items (name, path, size, mime_type).
    '''
    offset = 0
    while True:
        params = {"public_key": public_key, "offset": str(offset), "limit": "500"}
        if subpath:
            params["path"] = subpath
        data = api_get(params)
        if data.get("type") == "file":
            yield data
            return
        embedded = data.get("_embedded") or {}
        items = embedded.get("items") or []
        if not items:
            return
        for item in items:
            if item.get("type") == "dir":
                if depth < MAX_DIR_DEPTH:
                    yield from walk_public_folder(
                        public_key, item["path"], depth + 1
                    )
                else:
                    print(f"WARNING: skipping deep folder {item.get('name')}")
            else:
                yield item
        offset += len(items)
        total = int(embedded.get("total", offset))
        if offset >= total:
            return


def download_href(public_key: str, path: str) -> str:
    '''Return the temporary download URL for one public file.

    The endpoint occasionally answers without a href (rate limiting on
    the shared folder), so the call is retried.

    Args:
        public_key: Public link or hash of the shared folder.
        path: Path of the file inside the public folder (leading slash,
            as returned by the listing).

    Returns:
        Direct download href.
    '''
    last: str = "no attempts made"
    for attempt in range(ATTEMPTS):
        data = api_get({"public_key": public_key, "path": path})
        href = data.get("href")
        if href:
            return str(href)
        last = json.dumps(data)[:160]
        if attempt < ATTEMPTS - 1:
            time.sleep(RETRY_DELAY_SEC)
    raise SystemExit(f"ERROR: no download href for {path}: {last}")


def download_to(href: str, target: Path, size: int) -> None:
    '''Stream one file to disk.

    Args:
        href: Direct download URL.
        target: Local destination path.
        size: Expected size in bytes (for the progress line).
    '''
    request = urllib.request.Request(href, headers=USER_AGENT)
    last: Exception | None = None
    for attempt in range(ATTEMPTS):
        try:
            with _open_with_fallback(request) as response:
                with open(target, "wb") as stream:
                    shutil.copyfileobj(response, stream)
            last = None
            break
        except Exception as exc:  # noqa: BLE001 - any transport error retries
            # Remove the partial file so the next attempt starts clean.
            target.unlink(missing_ok=True)
            last = exc
            print(f"      attempt {attempt + 1}/{ATTEMPTS} failed: {exc}")
            time.sleep(RETRY_DELAY_SEC)
    if last is not None:
        raise SystemExit(f"ERROR: download failed for {target.name}: {last}")
    if target.stat().st_size != size:
        print(f"WARNING: {target.name} size mismatch after download")


def fmt_mb(size: int) -> str:
    '''Format a byte count as a compact MB string.

    Args:
        size: Size in bytes.

    Returns:
        Human-readable string like "12.3 MB".
    '''
    return f"{size / (1024 * 1024):.1f} MB"


def main(argv: list[str] | None = None) -> None:
    '''Entry point: resolve the link, list and download the documents.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:]).
    '''
    parser = argparse.ArgumentParser(
        description="Download issued PDFs/DOCX from the shared storage link "
        "(MANUALS_DOWNLOAD_URL; the link stays in the gitignored .env)."
    )
    parser.add_argument(
        "--url", default=None, help="override MANUALS_DOWNLOAD_URL (prefer .env)"
    )
    parser.add_argument(
        "--to", default=None, help="target dir (default: MANUALS_DIR or data/manuals)"
    )
    parser.add_argument(
        "--ext", default=",".join(DEFAULT_EXTS), help="comma-separated extensions"
    )
    parser.add_argument(
        "--include", default=None, help="download only names containing this substring"
    )
    parser.add_argument("--list", action="store_true", help="list contents only")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    env = read_env_file(repo_root)

    link = args.url or os.environ.get("MANUALS_DOWNLOAD_URL") or env.get(
        "MANUALS_DOWNLOAD_URL", ""
    )
    link = link.strip()
    if not link:
        raise SystemExit(
            "ERROR: MANUALS_DOWNLOAD_URL is not set.\n"
            "Put the shared storage link into .env (gitignored):\n"
            "  MANUALS_DOWNLOAD_URL=https://... \n"
            "The link must never be committed."
        )

    target = Path(
        args.to
        or os.environ.get("MANUALS_DIR")
        or env.get("MANUALS_DIR")
        or "data/manuals"
    )

    wanted_exts = tuple(
        "." + ext.lower().lstrip(".") for ext in args.ext.split(",") if ext.strip()
    )
    files = [
        item
        for item in walk_public_folder(link)
        if str(item.get("name", "")).lower().endswith(wanted_exts)
        and (args.include is None or args.include in str(item.get("name", "")))
    ]
    if not files:
        raise SystemExit(
            "ERROR: no matching files in the shared folder "
            f"(ext={','.join(wanted_exts)}, include={args.include!r})"
        )

    print(f"Shared folder: {len(files)} file(s) matching the filter")
    for item in files:
        print(f"  - {item.get('name')}  ({fmt_mb(int(item.get('size', 0)))})")
    if args.list:
        return

    target.mkdir(parents=True, exist_ok=True)
    fetched = skipped = 0
    for item in files:
        name = str(item["name"])
        dest = target / name
        size = int(item.get("size", 0))
        if dest.is_file() and dest.stat().st_size == size:
            print(f"SKIP  {name}  (already present)")
            skipped += 1
            continue
        print(f"GET   {name}  ({fmt_mb(size)}) ...", flush=True)
        href = download_href(link, str(item["path"]))
        download_to(href, dest, size)
        fetched += 1

    print(
        f"\nDone: {fetched} downloaded, {skipped} skipped -> {target.resolve()}"
    )
    print(
        "Next step (RAG): recognise, rename to manifest names and build the index:\n"
        f"  python -m rag.setup --from \"{target}\""
    )


if __name__ == "__main__":
    main()
