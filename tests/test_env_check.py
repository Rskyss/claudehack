"""真机环境自检工具（bin/env-check）的离线单元与边界测试。"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "bin" / "env-check"


def load_env_check_module():
    if not SCRIPT_PATH.exists():
        raise FileNotFoundError(f"缺少自检脚本: {SCRIPT_PATH}")
    loader = importlib.machinery.SourceFileLoader("env_check", str(SCRIPT_PATH))
    spec = importlib.util.spec_from_loader("env_check", loader)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 env-check 模块")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EnvCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cfg_path = Path(self.temp_dir.name) / "residential.json"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_config(self, data: dict, mode: int = 0o600) -> Path:
        self.cfg_path.write_text(json.dumps(data), encoding="utf-8")
        os.chmod(self.cfg_path, mode)
        return self.cfg_path

    def test_all_checks_pass_with_valid_environment(self) -> None:
        mod = load_env_check_module()
        secret_pwd = "super_secret_password_999"
        self._write_config(
            {
                "host": "198.51.100.25",
                "port": 12323,
                "username": "user_real",
                "password": secret_pwd,
                "expected_ip": "198.51.100.25",
                "local_proxy": "http://127.0.0.1:8121",
            },
            mode=0o600,
        )
        scutil_ok = (
            "<\n"
            "  ProxyAutoConfigEnable : 1\n"
            "  ProxyAutoConfigURLString : http://127.0.0.1:8899/proxy.pac?v=8\n"
            ">\n"
        )
        report = mod.run_checks(
            config_path=self.cfg_path,
            extension_dir=ROOT / "extension",
            port_checker=lambda host, port: True,
            pac_fetcher=lambda url: "function FindProxyForURL(url, host) { return 'DIRECT'; }",
            scutil_runner=lambda: scutil_ok,
            egress_fetcher=lambda proxy_url: "198.51.100.25",
        )
        self.assertTrue(report["ok"])
        text = mod.format_report(report)
        self.assertNotIn(secret_pwd, text)
        self.assertIn("浏览器内仍需手动确认扩展已启用", text)

    def test_placeholder_credentials_and_Never_leak_secret(self) -> None:
        mod = load_env_check_module()
        secret_pwd = "REPLACE_ME_SECRET_TOKEN"
        self._write_config(
            {
                "host": "203.0.113.10",
                "port": 12323,
                "username": "REPLACE_ME",
                "password": secret_pwd,
                "expected_ip": "203.0.113.10",
            },
            mode=0o600,
        )
        report = mod.run_checks(
            config_path=self.cfg_path,
            extension_dir=ROOT / "extension",
            port_checker=lambda host, port: True,
            pac_fetcher=lambda url: "function FindProxyForURL(url, host) {}",
            scutil_runner=lambda: "ProxyAutoConfigEnable : 1\nProxyAutoConfigURLString : http://127.0.0.1:8899/proxy.pac?v=8",
            egress_fetcher=lambda proxy_url: "203.0.113.10",
        )
        self.assertFalse(report["ok"])
        self.assertFalse(report["items"]["config"]["ok"])
        text = mod.format_report(report)
        self.assertNotIn(secret_pwd, text)

    def test_insecure_config_permissions_flagged(self) -> None:
        mod = load_env_check_module()
        self._write_config(
            {
                "host": "198.51.100.25",
                "port": 12323,
                "username": "user_real",
                "password": "pwd",
                "expected_ip": "198.51.100.25",
            },
            mode=0o644,
        )
        report = mod.run_checks(
            config_path=self.cfg_path,
            extension_dir=ROOT / "extension",
            port_checker=lambda host, port: True,
            pac_fetcher=lambda url: "function FindProxyForURL(url, host) {}",
            scutil_runner=lambda: "ProxyAutoConfigEnable : 1\nProxyAutoConfigURLString : http://127.0.0.1:8899/proxy.pac?v=8",
            egress_fetcher=lambda proxy_url: "198.51.100.25",
        )
        self.assertFalse(report["ok"])
        self.assertFalse(report["items"]["config"]["ok"])
        self.assertIn("0600", report["items"]["config"]["detail"])

    def test_missing_service_or_unmounted_pac_fails(self) -> None:
        mod = load_env_check_module()
        self._write_config(
            {
                "host": "198.51.100.25",
                "port": 12323,
                "username": "user_real",
                "password": "pwd",
                "expected_ip": "198.51.100.25",
            },
            mode=0o600,
        )
        report = mod.run_checks(
            config_path=self.cfg_path,
            extension_dir=ROOT / "extension",
            port_checker=lambda host, port: port != 8687,
            pac_fetcher=lambda url: "function FindProxyForURL(url, host) {}",
            scutil_runner=lambda: "ProxyAutoConfigEnable : 0",
            egress_fetcher=lambda proxy_url: "198.51.100.25",
        )
        self.assertFalse(report["ok"])
        self.assertFalse(report["items"]["services"]["ok"])
        self.assertFalse(report["items"]["browser_pac"]["ok"])

    def test_egress_ip_mismatch_fails(self) -> None:
        mod = load_env_check_module()
        self._write_config(
            {
                "host": "198.51.100.25",
                "port": 12323,
                "username": "user_real",
                "password": "pwd",
                "expected_ip": "198.51.100.25",
            },
            mode=0o600,
        )
        report = mod.run_checks(
            config_path=self.cfg_path,
            extension_dir=ROOT / "extension",
            port_checker=lambda host, port: True,
            pac_fetcher=lambda url: "function FindProxyForURL(url, host) {}",
            scutil_runner=lambda: "ProxyAutoConfigEnable : 1\nProxyAutoConfigURLString : http://127.0.0.1:8899/proxy.pac?v=8",
            egress_fetcher=lambda proxy_url: "198.51.100.99",
        )
        self.assertFalse(report["ok"])
        self.assertFalse(report["items"]["egress"]["ok"])
        self.assertIn("不一致", report["items"]["egress"]["detail"])

    def test_chrome_policy_pac_accepted_when_scutil_disabled(self) -> None:
        mod = load_env_check_module()
        self._write_config(
            {
                "host": "198.51.100.25",
                "port": 12323,
                "username": "user_real",
                "password": "pwd",
                "expected_ip": "198.51.100.25",
            },
            mode=0o600,
        )
        chrome_policy_ok = (
            '{\n'
            '    ProxyMode = "pac_script";\n'
            '    ProxyPacMandatory = 1;\n'
            '    ProxyPacUrl = "http://127.0.0.1:8899/proxy.pac?v=8";\n'
            '}\n'
        )
        report = mod.run_checks(
            config_path=self.cfg_path,
            extension_dir=ROOT / "extension",
            port_checker=lambda host, port: True,
            pac_fetcher=lambda url: "function FindProxyForURL(url, host) {}",
            scutil_runner=lambda: "ProxyAutoConfigEnable : 0",
            chrome_policy_runner=lambda: chrome_policy_ok,
            egress_fetcher=lambda proxy_url: "198.51.100.25",
        )
        self.assertTrue(report["items"]["browser_pac"]["ok"])
        self.assertTrue(report["ok"])

    def test_missing_extension_dir_fails_instead_of_false_positive(self) -> None:
        mod = load_env_check_module()
        self._write_config(
            {
                "host": "198.51.100.25",
                "port": 12323,
                "username": "user_real",
                "password": "pwd",
                "expected_ip": "198.51.100.25",
            },
            mode=0o600,
        )
        missing_ext = Path(self.temp_dir.name) / "nonexistent_extension"
        report = mod.run_checks(
            config_path=self.cfg_path,
            extension_dir=missing_ext,
            port_checker=lambda host, port: True,
            pac_fetcher=lambda url: "function FindProxyForURL(url, host) {}",
            scutil_runner=lambda: "ProxyAutoConfigEnable : 1\nProxyAutoConfigURLString : http://127.0.0.1:8899/proxy.pac?v=8",
            egress_fetcher=lambda proxy_url: "198.51.100.25",
        )
        self.assertFalse(report["items"]["extension"]["ok"])
        self.assertFalse(report["ok"])

    def test_null_fields_and_credential_in_local_proxy_rejected_without_leak(self) -> None:
        mod = load_env_check_module()
        leaked_token = "leak_token_777"
        self._write_config(
            {
                "host": None,
                "port": 12323,
                "username": "user_real",
                "password": "pwd",
                "expected_ip": "198.51.100.25",
                "local_proxy": f"http://user:{leaked_token}@127.0.0.1:8121",
            },
            mode=0o600,
        )
        report = mod.run_checks(
            config_path=self.cfg_path,
            extension_dir=ROOT / "extension",
            port_checker=lambda host, port: True,
            pac_fetcher=lambda url: "function FindProxyForURL(url, host) {}",
            scutil_runner=lambda: "ProxyAutoConfigEnable : 1\nProxyAutoConfigURLString : http://127.0.0.1:8899/proxy.pac?v=8",
            egress_fetcher=lambda proxy_url: "198.51.100.25",
        )
        self.assertFalse(report["items"]["config"]["ok"])
        text = mod.format_report(report)
        self.assertNotIn(leaked_token, text)


if __name__ == "__main__":
    unittest.main()
