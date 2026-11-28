"""Compare candidate-bound delivery bytes with prepared release assets."""

import hashlib
import json
import pathlib
import re

from runtime import Refused, require, tool


ASSET = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def check_assets(repo, director, candidate, asset_dir, assets):
    receipt = director / "evidence" / "DELIVERY.json"
    payload = receipt.read_bytes()
    require(tool("delivery", "check", "--repo", repo, "--director", director, "--delivered", candidate),
            "交付證據", "DELIVERY_CHECK: PASS")
    records = {item["path"]: item for item in json.loads(payload)["files"]}
    found = {}
    root = asset_dir.resolve(strict=True)
    for source, name in assets:
        if (not ASSET.fullmatch(name) or name.endswith(".") or pathlib.PureWindowsPath(name).is_reserved()
                or name.casefold() in found or source not in records):
            raise Refused("資產檔名重複或無效，或來源缺少候選交付紀錄")
        path = root / name
        if path.resolve() != path or not path.is_file():
            raise Refused(f"找不到指定位置的資產：{name}")
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)
        item = records[source]
        if digest.hexdigest() != item["sha256"] or size != item["bytes"]:
            raise Refused(f"資產和驗過的交付檔不同：{name}")
        found[name.casefold()] = name
    if receipt.read_bytes() != payload:
        raise Refused("驗證時交付紀錄已變更")
    return list(found.values())
