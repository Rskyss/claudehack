# claudehack

macOS 上的本地 HTTP 代理网关、SOCKS5 域名分流、PAC 与 Chrome 扩展源码。这个仓库保存已在本机使用的组件及最小维护修复，提供脱敏配置示例，不包含真实代理凭据、账号资料、浏览器配置文件或运行日志。

## 组件

| 路径 | 用途 |
| --- | --- |
| `gateway/retry_proxy.py` | HTTP / CONNECT 网关，监听 `127.0.0.1:8121`，通过配置指定的上游代理转发 |
| `gateway/split_proxy.py` | SOCKS5 分流，监听 `127.0.0.1:8687`；保护域名经 HTTP 网关，其他目标走系统默认网络 |
| `gateway/proxy.pac` | 78 个保护域名后缀、10 个豁免子域；保护目标的 PAC 返回值不包含 DIRECT |
| `gateway/pac_server.py` | 在 `127.0.0.1:8899` 提供 PAC |
| `extension/` | 现有 Chrome 扩展 v2.3.0；匹配页面的语言/时区设置及 WebRTC 限制 |
| `bin/` | Claude CLI 启动包装器及独立配置目录入口 |
| `macos/` | 系统代理守护脚本、Swift helper 源码模板和 launchd 模板 |
| `tests/` | 不读取真实凭据、不访问外网的回归测试 |

## 这次维护修复了什么

1. 网关配置丢失、损坏或必要字段无效时拒绝新连接，移除源码中的备用凭据。
2. 竞速连接超时结束与成功 socket 移交使用同一把锁，避免调用方退出后仍产生无人接收的成功连接；转发失败时关闭已取得的上游连接。
3. root 守护脚本与 helper 放到 `/Library/PrivilegedHelperTools/local.claude-residential/`，由 root 拥有；root 日志使用 `/var/log/claude-residential-proxy-guard.log`。不再让 root 从用户可写目录执行脚本或二进制。

现有分流名单、代理端口、并发数、重试次数、超时参数与扩展行为没有因这次维护而调整。公开版仅把机器路径改为用户目录或模板占位符，并使用示例地址替代实际出口。

## 本地配置与运行

需要 Python 3.9+；使用 macOS helper 时需要 Swift 编译器。测试只使用 Python 标准库。

以下用于新环境手动配置，**已运行正常的环境无需重复安装或重置浏览器**。

```sh
mkdir -p "$HOME/.config/claude-residential/bin"
chmod 700 "$HOME/.config/claude-residential"
cp gateway/*.py gateway/proxy.pac "$HOME/.config/claude-residential/"
cp bin/* "$HOME/.config/claude-residential/bin/"
# 只在配置尚不存在时创建示例，避免覆盖既有凭据。
if [ ! -e "$HOME/.config/claude-residential/residential.json" ]; then
  (umask 077; cp config/residential.example.json "$HOME/.config/claude-residential/residential.json")
fi
chmod 600 "$HOME/.config/claude-residential/residential.json"
```

编辑 `residential.json`，填写自己的上游地址、端口、用户名、密码及预期出口 IP。示例 `203.0.113.10` 是文档地址，不能用于真实联网。文件权限保护不等于加密存储。`expires_at` 只是维护记录，当前没有按到期日期自动提醒的功能。

在三个终端中分别启动：

```sh
python3 "$HOME/.config/claude-residential/retry_proxy.py"
python3 "$HOME/.config/claude-residential/split_proxy.py"
python3 "$HOME/.config/claude-residential/pac_server.py"
```

通过网关检查出口：

```sh
curl --noproxy '' --proxy http://127.0.0.1:8121 https://api.ipify.org
```

浏览器使用 PAC 地址 `http://127.0.0.1:8899/proxy.pac?v=8`。需要强制 PAC 时，由管理员配置 Chrome 的 `ProxySettings`（`ProxyMode=pac_script`、`ProxyPacMandatory=true`、`ProxyPacUrl` 为上述地址）；不要覆盖已有的其他管理策略。独立 Chrome 配置文件中可通过 `chrome://extensions` 加载 `extension/`。

CLI 包装器默认调用 `$HOME/.local/bin/claude`。把 `$HOME/.config/claude-residential/bin` 放在 PATH 前面即可使用。启动前核验出口和代理环境变量不能代替操作系统级网络隔离；`--help`、`--version` 不联网检查。运行本仓库的测试不需要安装或登录 Claude。

## macOS 常驻服务与权限

`macos/launchd/` 的三个 LaunchAgent 模板需要先替换：

- `__USER_HOME__`：用户目录绝对路径。
- `__PYTHON__`：所用 Python 3.9+ 的可执行文件绝对路径。

替换后检查 plist，再安装到该用户的 `~/Library/LaunchAgents/`。模板不是开箱即用的系统配置，仓库不自动覆盖或启用机器的服务。

如果已有 VPN 会覆盖系统 PAC，可使用 `macos/proxy-guard.sh` 配合 Swift helper。先把 `macos/install-proxy.swift.template` 中的 `__USER_HOME__` 替换为实际目录，在普通用户权限下编译；**管理员安装时必须将脚本和编译结果复制到 root 拥有、普通用户不可写的上述系统目录**，不能用指向用户目录的软链接。文件及目录权限使用 0755，LaunchDaemon plist 使用 root:wheel / 0644，日志使用 root:wheel / 0600。

LaunchDaemon 使用仓库中的 `local.claude-residential-proxy-guard.plist`。启用前核对路径、权限和 `plutil -lint` 结果。helper 仍从该用户目录读取 PAC 内容作为配置数据；root 执行的脚本与二进制必须独立受保护。更新 helper 后也应重新由管理员安装，不要把运行路径改回用户可写目录。

## 测试和验收范围

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
node --check extension/shield.js
bash -n macos/proxy-guard.sh
```

2026-10-31 本机维护验证了配置异常、正常热加载、CONNECT 成功、拒绝连接重试上限、超时后的迟到连接以及转发异常清理。临时与正式网关的出口核验通过；Stripe 脚本返回 200。未登录的命令行探测对 Claude、Persona 完成 TLS 连接但得到 HTTP 403，这不代表账号或付款已通过验证。

范围限制：

- 只有已列入名单且实际使用这些代理组件的请求受分流规则约束；新增的第三方域名和银行验证页面不保证覆盖。
- Chrome 配置文件提供存储层面的逻辑隔离，不是独立硬件或操作系统。
- 扩展的 Worker 注入只覆盖部分非 module 的 blob/data Worker；外部 URL、module Worker 和所有 Date 方法未完整覆盖。
- 本地连通、IP 检测与第三方信誉分不能证明平台不会要求 KYC、验证码或银行卡认证。
- 手机内购不能被承诺为免 KYC 通道。账单地址应填写发卡行登记的真实地址，不应按代理 IP 所在城市填写。

参考：[Claude 身份认证说明](https://support.claude.com/en/articles/14328960-identity-verification-on-claude)、[Stripe 账单地址核验](https://docs.stripe.com/disputes/prevention/verification)。
