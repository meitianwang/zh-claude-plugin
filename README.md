# Claude Desktop 简体中文补丁（macOS）

为 macOS 版 **Claude Desktop** 添加简体中文界面。官方界面语言目前只有 11 种（英、法、德、印地、印尼、意、日、韩、葡、两种西语），不含中文 —— 这个项目把界面补成中文。

与现有社区方案相比，本项目：

- **全程不需要 sudo** —— 个人安装的 `Claude.app` 属主就是你自己，可直接修改。
- **官方账号登录可用** —— 不改第三方推理（3P）校验，不影响官方登录。
- **覆盖接近 100%** —— 在你机器实测的版本上，社区静态语料只覆盖 ~66%；本项目用 Claude 把缺口字符串补翻入语料，做到当前版本接近全中文。
- **更新后自动重打补丁** —— 可选的用户级 LaunchAgent，在 Claude 自动更新还原补丁后自动重新汉化并通知你。
- **结构化匹配 + 失败隔离** —— 单个锚点在新版漂移时只降级对应功能，不会让整次汉化失败。
- **一键回滚** —— 安装前整包时间戳备份，卸载即恢复。

> ⚠️ **这是非官方补丁，与 Anthropic 无关。** 它会修改本机 `Claude.app` 并以 ad-hoc 签名重签，请阅读下方「风险」一节后再决定使用。

## 一键配置（最简）

```bash
git clone https://github.com/meitianwang/zh-claude-plugin.git
cd zh-claude-plugin
./install.command
```

或下载 zip 解压后，**右键 `install.command` → 打开**（首次需如此绕过 macOS Gatekeeper，之后正常双击）。

脚本会自动补齐前置条件：缺 `python3` 时触发安装「命令行工具」并等待；未装 Claude 时打开官方下载页并等待你装好，然后自动继续。

> 覆盖率说明：语料针对某个 Claude 版本校准。你的 Claude 若**不新于**该版本，基本 100% 中文；若**更新**，新增字符串会先显英文，运行 `./bin/claude-zh translate`（需本机有 `claude` CLI 或 API key）即可用 Claude 补满。

## 安装

要求：macOS、已安装 Claude Desktop、系统自带 `/usr/bin/python3`（Xcode Command Line Tools 即可）。

```bash
# 终端方式
./bin/claude-zh status        # 先看看当前状态与覆盖率
./bin/claude-zh install       # 安装（会退出并替换 Claude.app，原版自动备份）
```

或双击 `install.command`。

安装后打开 Claude，如果没自动切换，在左下角头像菜单 **Language → 简体中文**。

### 可选：更新后自动重打补丁

Claude 会通过 Squirrel 自动更新，更新会把整个 app 换成全新官方版、**抹掉补丁**。装一个用户级守护代理来自动恢复：

```bash
./bin/claude-zh install                 # 先装补丁
./bin/claude-zh autopatch install        # 再装自动重打代理（顺序重要）
./bin/claude-zh autopatch status         # 查看状态
```

代理监听 `Claude.app/Contents/Info.plist`；更新替换 app 后会触发，检测到中文目录消失就用你上次的选项重新打补丁并发系统通知。

> 不用 `disableAutoUpdates` 禁更新：那个 MDM 键会让 Claude 把设备当成「受组织管理」，连带锁掉无关设置。靠「更新后重打」更干净。

## 卸载

```bash
./bin/claude-zh autopatch uninstall   # 先移除自动重打代理（否则它会再次打补丁）
./bin/claude-zh uninstall             # 恢复最近一次备份，locale 切回 en-US
```

或双击 `uninstall.command`（已包含上面两步）。

## 命令

| 命令 | 作用 |
|---|---|
| `claude-zh status` | 显示版本、是否可写（免 sudo）、签名状态、覆盖率、备份数 |
| `claude-zh install` | 打补丁（`--dry-run` 只在临时副本上构建+验签不动正式 app；`--no-online` 跳过远程页面翻译，不碰 app.asar；`--launch` 装后启动） |
| `claude-zh uninstall` | 从备份恢复原版 |
| `claude-zh translate` | 检测新版新增、语料没覆盖的字符串，用 Claude 补翻并写入语料扩展（`--dry-run` 只报告缺口） |
| `claude-zh autopatch install\|uninstall\|status\|run` | 管理更新后自动重打代理 |

## 原理

界面分两层（这是关键事实）：

1. **本地外壳 / 菜单 / 设置 / 前端目录** —— 字符串在 `Claude.app/Contents/Resources` 的松散文件里。补丁做的是：
   - 在前端 JS 的语言白名单数组里加入 `zh-CN`（用结构化正则匹配，扛得住版本变化）；
   - 覆盖 `Intl.DisplayNames`，让选择器显示「简体中文」；
   - 把语料对当前版本的 `en-US.json` **现场合并**写出 `ion-dist/i18n/zh-CN.json`（没翻的 key 回退英文，绝不空白）；
   - 写出外壳目录 `Resources/zh-CN.json`（外壳扫目录自动发现语言）和原生菜单 `zh-CN.lproj/Localizable.strings`；
   - 写 `~/Library/Application Support/Claude/config.json` 的 `locale=zh-CN`（在 bundle 外，无签名影响）。

2. **远程 claude.ai 页面** —— 官方账号登录后，主聊天区是 Electron 加载的远程网页，本地语言文件管不到它，而 claude.ai 官方不提供中文。所以补丁向 `app.asar` 的主进程 `dom-ready` 钩子注入一段**显示层 DOM 翻译**脚本：用翻译映射改写页面可见文本和 `aria-label/title/placeholder` 属性，并用 MutationObserver 跟进动态内容。**只改界面文本，不碰任何网络请求、响应、模型路由或页面逻辑。** 这是唯一会改 `app.asar` 的步骤，可用 `--no-online` 关闭。

改 `app.asar` 后会按 Electron 规范重算每文件 SHA-256（含 4 MiB 分块）和头部哈希并写回 `Info.plist`，否则应用拒绝启动。

## 风险（请务必了解）

- **会破坏 Apple 签名。** 所有语言文件都在代码签名密封内，改任何一个都会使官方 Developer ID 签名失效。补丁因此对整个 bundle 做 **ad-hoc 重签** 并清除 Gatekeeper quarantine 属性 —— 这是做中文界面无法绕开的代价。
- **可能影响 Cowork。** ad-hoc 签名没有 Team ID，Cowork 的虚拟机服务可能拒绝（表现为 "RPC pipe closed"）。**装后请立刻验证 Cowork 工作区能否启动；不行就 `claude-zh uninstall` 一键回滚。**
- **更新会短暂还原。** 自动更新后、自动重打代理触发前的窗口里，界面可能短暂回到英文（`config.json` 的 `locale=zh-CN` 此时指向缺失目录，直到重打）。
- **远程页面翻译是显示层。** 页面结构大改时可能漏翻，靠 `claude-zh translate` + 语料更新跟进。

## 协议

- 补丁**代码**：MIT（见 `LICENSE`）。
- 翻译**语料**：CC BY-NC-SA 4.0，种子语料来自 [Pheo Hu / Claude_zh-CN_LanguagePack](https://github.com/pheohu-42/Claude_zh-CN_LanguagePack)，Claude 补翻部分同协议。详见 `NOTICE`。非商用、署名、相同方式共享。
