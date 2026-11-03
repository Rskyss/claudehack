"""保护域名五处名单必须一致：PAC、SOCKS、扩展 rules、manifest 权限与注入范围。"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MUSE_META = (
    "muse.ai",
    "meta.ai",
    "meta.com",
    "metaaivm.com",
    "metaaiusercontent.com",
    "ecto1usercontent.com",
    "meta-agents-apps.workers.dev",
    "facebook.com",
    "facebook.net",
    "fbcdn.net",
    "fbsbx.com",
    "instagram.com",
    "cdninstagram.com",
)


def _pac_domains() -> list[str]:
    text = (ROOT / "gateway" / "proxy.pac").read_text(encoding="utf-8")
    block = re.search(
        r"var residentialDomains = \[([\s\S]*?)\];",
        text,
    )
    if not block:
        raise AssertionError("proxy.pac 缺少 residentialDomains")
    return re.findall(r'"([^"]+)"', block.group(1))


def _socks_domains() -> list[str]:
    text = (ROOT / "gateway" / "split_proxy.py").read_text(encoding="utf-8")
    block = re.search(r"^SUFFIXES = \(([\s\S]*?)^\)\n", text, re.MULTILINE)
    if not block:
        raise AssertionError("split_proxy.py 缺少 SUFFIXES")
    return re.findall(r'"([^"]+)"', block.group(1))


def _rules_domains() -> list[str]:
    rules = json.loads((ROOT / "extension" / "rules.json").read_text(encoding="utf-8"))
    found: list[str] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            if "requestDomains" in node and isinstance(node["requestDomains"], list):
                found.extend(node["requestDomains"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(rules)
    return found


def _manifest_host_roots() -> set[str]:
    manifest = json.loads((ROOT / "extension" / "manifest.json").read_text(encoding="utf-8"))
    roots: set[str] = set()
    pattern = re.compile(r"^\*://(?:\*\.)?([^/]+)/\*$")
    for key in ("host_permissions",):
        for entry in manifest.get(key, []):
            match = pattern.match(entry)
            if match:
                roots.add(match.group(1))
    for script in manifest.get("content_scripts", []):
        for entry in script.get("matches", []):
            match = pattern.match(entry)
            if match:
                roots.add(match.group(1))
    return roots


class DomainListConsistencyTests(unittest.TestCase):
    def test_pac_socks_rules_same_ordered_list(self) -> None:
        pac = _pac_domains()
        socks = _socks_domains()
        rules = _rules_domains()
        self.assertEqual(pac, socks)
        self.assertEqual(pac, rules)
        self.assertEqual(len(pac), 91)

    def test_muse_meta_suffixes_present(self) -> None:
        pac = set(_pac_domains())
        missing = [domain for domain in MUSE_META if domain not in pac]
        self.assertEqual(missing, [])

    def test_manifest_covers_every_protected_suffix(self) -> None:
        roots = _manifest_host_roots()
        missing = [domain for domain in _pac_domains() if domain not in roots]
        self.assertEqual(missing, [])

    def test_extension_version_is_2_4_0(self) -> None:
        manifest = json.loads((ROOT / "extension" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest.get("version"), "2.4.0")
        shield = (ROOT / "extension" / "shield.js").read_text(encoding="utf-8")
        self.assertIn("v2.4.0", shield.splitlines()[0])


if __name__ == "__main__":
    unittest.main()
