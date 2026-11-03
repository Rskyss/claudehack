# AI 辅助安装与全环境体检指南

本文档专为协助用户部署本项目的 AI 助手（如 Claude Code、Cursor、Windsurf、Codex 等）编写。当用户将本仓库交给你并要求“帮我安装/配置/检查环境”时，请按本指南自动完成本地部署、浏览器分流接入与真机自检，并用通俗易懂的中文与用户沟通。

---

## 0. 必须遵守的安全与诚实边界

1. **面向非技术用户沟通**：默认用户不熟悉命令行与网络配置。需要用户提供信息或手动点击浏览器时，用简明中文分步引导，不要让用户自己拼写复杂命令或手动编辑 JSON。
2. **凭据绝对隔离**：用户提供的代理服务器地址、端口、账号、密码只允许写入用户本机的 `$HOME/.config/claude-residential/residential.json`（目录权限 `0700`，文件权限 `0600`）。**严禁写入仓库内的 `config/residential.example.json` 或任何 Git 跟踪文件，严禁在聊天总结或日志中回显明文密码，严禁提交或推送凭据。**
3. **保护已有环境**：操作前先运行 `python3 bin/env-check`（或带 `--offline`）检查本机现状。若本机已存在 `$HOME/.config/claude-residential/residential.json` 且环境正常，直接告知用户无需重复安装；若需更换代理或覆盖配置，必须先征得用户同意并备份原文件。
4. **特权目录边界**：三个核心代理服务必须以**普通用户身份**运行。仅当用户的日常 VPN 会覆盖系统 PAC 且用户明确要求部署防覆盖守护（`proxy-guard`）时，才涉及管理员权限；此时 root 执行的脚本与编译产物必须放在 `root:wheel` 拥有、普通用户不可写的 `/Library/PrivilegedHelperTools/local.claude-residential/`，严禁使用指向用户目录的软链接。
5. **如实报告检查结果**：
   - `python3 -m unittest` 仅检查仓库代码逻辑，不代表用户机器环境已配好。
   - `python3 bin/env-check` 用于检查本机配置、三个本地服务、系统 PAC 挂载、扩展文件与代理出口连通性。
   - Chrome 扩展必须在浏览器内手动加载并刷新页面后才生效；网络连通或出口匹配不代表平台免验证码、免 KYC 或支付必然成功。

---

## 1. 第一步：确认用户的安装目标

开始操作前，先检查本机状态，并向用户确认需要哪一种安装范围（如用户已明确要求“本地和浏览器全套环境”，直接进入**路线 B**）：

| 路线 | 适用场景 | 包含内容 | 用户需准备 |
| :--- | :--- | :--- | :--- |
| **路线 A：仅安装 Chrome 护盾插件** | 只需要网页语言设置与 WebRTC 非代理 UDP 限制，不需要本地代理分流 | 引导加载 `extension/` 文件夹 | Chrome 浏览器 |
| **路线 B：本地代理 + 域名分流 + 浏览器护盾全环境** | 需要为 Claude、Muse/Meta AI、Google、Stripe 等 91 个保护域名配置固定住宅代理出口，同时保留日常网络分流 | 本地 3 个常驻服务 + 系统/浏览器 PAC 挂载 + Chrome 护盾插件 + 真机出口自检 | macOS、Python 3.9+、Chrome、自备可用的上游 HTTP 住宅代理凭据（国内网络通常还需开启日常前置出海 VPN） |

---

## 2. 路线 A 执行流程（仅安装 Chrome 浏览器插件）

1. **确认固定存放目录**：确认当前仓库位于用户准备长期保留的位置（如 `$HOME/Applications/claudehack` 或文稿/桌面固定目录）。若在系统临时目录，先帮用户复制到固定路径，避免日后删除导致扩展失效。
2. **校验扩展文件**：确认 `extension/manifest.json`、`extension/shield.js`、`extension/rules.json`、`extension/background.js` 齐全（当前版本 `2.4.0`）。
3. **打开目录并引导用户加载**：
   - 在 macOS 上运行 `open -R "<仓库路径>/extension/manifest.json"`，帮用户在访达（Finder）中直接高亮定位 `extension` 文件夹。
   - 用通俗中文提示用户在 Chrome 中完成以下 4 步：
     1. 打开要使用的 Chrome 窗口，在地址栏输入 `chrome://extensions` 并回车。
     2. 打开页面右上角的 **“开发者模式”** 开关。
     3. 点击左上角 **“加载已解压的扩展程序”**，选择刚才高亮的 **`extension` 文件夹**（注意：选择 `extension` 文件夹本身，不要选外层总文件夹或 ZIP 压缩包）。
     4. 确认列表出现 **Claude 美区住宅安全护盾**（版本 **2.4.0**）且开关已启用，然后刷新目标网页。
   - 提醒用户：仅安装插件不会改变网络出口 IP；WebRTC 策略作用于该 Chrome 配置文件内的所有网页。

---

## 3. 路线 B 执行流程（本地 + 浏览器全环境整理）

### 3.1 环境预检与收集代理信息

1. 检查系统环境：确认当前系统为 macOS，且 `python3`（3.9+）、`curl`、`plutil` 可用。
2. 若 `$HOME/.config/claude-residential/residential.json` 尚不存在（或仍为示例占位符），请用户直接在对话框中提供自备的**上游 HTTP 住宅代理信息**：
   - **代理服务器地址**（`host`）
   - **代理端口**（`port`）
   - **代理账号**（`username`）
   - **代理密码**（`password`）
   - **到期日期**（可选，`expires_at`，格式 `YYYY-MM-DD`，仅作本地维护记录）

### 3.2 安装本地文件、启动服务并自动锁定出口 IP

为避免在命令行参数或系统进程表中暴露明文密码，同时也避免密码含特殊字符导致 URL 解析失败，请严格按以下顺序操作：

1. **创建私密目录并拷贝组件**：
   ```sh
   mkdir -p "$HOME/.config/claude-residential/bin"
   chmod 700 "$HOME/.config/claude-residential"
   cp gateway/*.py gateway/proxy.pac "$HOME/.config/claude-residential/"
   cp bin/* "$HOME/.config/claude-residential/bin/"
   chmod +x "$HOME/.config/claude-residential/bin/"*
   ```
2. **写入初始私密配置并锁定 `0600` 权限**：
   - 将用户提供的 `host`、`port`、`username`、`password` 写入 `$HOME/.config/claude-residential/residential.json`（`local_proxy` 设为 `"http://127.0.0.1:8121"`，`timezone` 设为 `"America/New_York"`，`locale` 设为 `"en_US.UTF-8"`，`expected_ip` 先填入待更新值或 `host`）。
   - 立即执行 `chmod 600 "$HOME/.config/claude-residential/residential.json"`。
   - **安全要求**：通过文件写入（如 Python `json.dump`）生成该 JSON，不要在 Shell 命令行参数中拼接明文密码。

### 3.3 配置并启动本地 3 个后台常驻服务（LaunchAgent），再自动测出真实 `expected_ip`

1. 获取当前用户的 `$HOME` 绝对路径与 `python3` 可执行文件绝对路径（如 `command -v python3`），并确保目录存在：
   ```sh
   mkdir -p "$HOME/Library/LaunchAgents"
   ```
2. 读取 `macos/launchd/` 下的三个 LaunchAgent 模板：
   - `local.claude-residential-retry.plist`（HTTP / CONNECT 网关，`127.0.0.1:8121`）
   - `local.claude-residential-split.plist`（SOCKS5 分流，`127.0.0.1:8687`）
   - `local.claude-residential-pac.plist`（PAC 服务，`127.0.0.1:8899`）
3. 将模板中的 `__USER_HOME__` 与 `__PYTHON__` 替换为实际绝对路径，写入 `$HOME/Library/LaunchAgents/`（不要直接修改仓库内的模板文件）。
4. 使用 `plutil -lint` 校验三个 plist 文件语法，然后加载并启动服务：
   ```sh
   for label in local.claude-residential-retry local.claude-residential-split local.claude-residential-pac; do
     plist="$HOME/Library/LaunchAgents/${label}.plist"
     plutil -lint "$plist"
     launchctl bootout "gui/$(id -u)" "$plist" 2>/dev/null || true
     launchctl bootstrap "gui/$(id -u)" "$plist"
     launchctl kickstart -k "gui/$(id -u)/${label}"
   done
   ```
5. **经本地网关自动探测真实出口 IP 并写回 `expected_ip`**（免去用户手查 IP，且命令行不暴露密码）：
   - 本地 `8121` 网关支持热加载 `residential.json`。直接通过本地网关查询实际公网出口 IP：
     ```sh
     curl -sS --noproxy '' --connect-timeout 8 --max-time 12 -x http://127.0.0.1:8121 https://api.ipify.org
     ```
     （若 `api.ipify.org` 未响应，改用 `https://ipinfo.io/ip`。）
   - 若连接超时或失败，用通俗语言提示用户排查：**① 国内网络下日常前置 VPN 是否已开启；② 代理地址、端口、账号密码是否正确且未到期。**
   - 拿到返回的公网 IP 后，将其更新写入 `$HOME/.config/claude-residential/residential.json` 的 `expected_ip` 字段（保持文件权限 `0600`）。

### 3.4 整理浏览器环境（挂载 PAC 分流 + 引导加载护盾插件）

浏览器环境需要**“网络分流（PAC）”**和**“页面护盾（Chrome 插件）”**同时就绪：

1. **挂载系统 / 浏览器自动代理（PAC）**：
   - PAC 地址固定为：`http://127.0.0.1:8899/proxy.pac?v=8`。
   - 可通过 `networksetup -listallnetworkservices` 查看当前活跃网络服务（常见为 `Wi-Fi` 或 `Ethernet`），在征得用户同意后将该网络服务的自动代理配置设为上述 PAC 地址并开启：
     ```sh
     networksetup -setautoproxyurl "Wi-Fi" "http://127.0.0.1:8899/proxy.pac?v=8"
     networksetup -setautoproxystate "Wi-Fi" on
     ```
   - 若用户的日常 VPN 会自动清空或覆盖系统 PAC，告知用户可选择：
     - 在 Chrome 管理策略（`ProxySettings`）中配置 `ProxyMode=pac_script`、`ProxyPacMandatory=true`、`ProxyPacUrl=http://127.0.0.1:8899/proxy.pac?v=8`；或
     - 按 [README.md](../README.md#macos-常驻部署) 的说明，经管理员授权部署 root 级 `proxy-guard` 守护服务。
2. **引导建立独立 Chrome 配置文件并加载 `extension` 插件**：
   - 建议用户在 Chrome 右上角头像菜单新建一个**独立 Chrome 配置文件（分身窗口）**，避免与日常旧账号 Cookie 混用。
   - 按上文**第 2 节（路线 A）**的步骤，帮用户在 Finder 中高亮 `extension` 文件夹，引导用户在 `chrome://extensions` 中开启开发者模式并加载 `extension` 文件夹（确认版本 `2.4.0` 启用）。

### 3.5（可选）配置终端 Claude CLI 出口门禁

若用户同时使用终端 `claude` 命令：
1. 确认底层 `$HOME/.local/bin/claude` 已安装。
2. 提示或协助用户将 `export PATH="$HOME/.config/claude-residential/bin:$PATH"` 加入 `~/.zshrc`，使 `claude`、`claude-a`、`claude-b` 启动前自动校验住宅出口 IP。

---

## 4. 第四步：运行真机环境自检并向用户汇报

完成部署后，必须运行真机自检工具验证实际环境状态（而不是只跑离线单元测试）：

```sh
# 在仓库根目录直接运行
python3 bin/env-check

# 若从安装后的 ~/.config/claude-residential/bin 目录运行，请显式指定仓库 extension 文件夹路径
python3 "$HOME/.config/claude-residential/bin/env-check" --extension-dir "<仓库路径>/extension"
```

根据自检输出，用通俗中文向用户汇总：
1. **已自动就绪的项目**：本地住宅配置（权限 `0600`）、三个后台常驻服务（8121 / 8687 / 8899）、系统 PAC 分流挂载状态、以及经本地网关实测的美国住宅出口 IP。
2. **需用户在浏览器内最终确认的项目**：
   - 在 `chrome://extensions` 中确认 **Claude 美区住宅安全护盾（v2.4.0）** 已启用；
   - 在该 Chrome 窗口打开 `https://ippure.com` 或 `https://ip.sb`，确认页面显示的出口 IP 与配置的住宅 IP 一致，再打开或刷新目标站点。
3. **能力边界提醒**：如实说明本工具负责本地分流、出口校验与页面语言/WebRTC 设置，不能保证平台免除验证码、身份认证（KYC）或银行卡 3DS 验证；支付账单地址应填写发卡行登记的真实地址。
