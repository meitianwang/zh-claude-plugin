#!/bin/bash
# Double-click entry point: install the Simplified Chinese UI for Claude Desktop.
# Designed to be as foolproof as macOS allows — no sudo, friendly preflight checks.
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
err()  { printf '\033[31m%s\033[0m\n' "$1"; }
pause() { echo; read -r -p "按回车退出… " _ ; }

bold "==== Claude Desktop 简体中文补丁 ===="
echo

# 0) Downloaded from the internet? Strip Gatekeeper quarantine from this folder so
#    the bundled scripts run without "unidentified developer" prompts on later runs.
xattr -cr "$DIR" 2>/dev/null || true

# 1) Need Apple's python3 (ships with Xcode Command Line Tools). Auto-provision it.
if ! /usr/bin/python3 --version >/dev/null 2>&1; then
  bold "未检测到 python3,正在为你触发安装「命令行工具」(会弹出系统安装窗口)…"
  xcode-select --install >/dev/null 2>&1 || true
  echo "请在弹窗里点「安装」并等待完成 —— 本脚本会自动继续(按 Ctrl-C 可取消)。"
  while ! /usr/bin/python3 --version >/dev/null 2>&1; do
    sleep 5; printf '.'
  done
  echo; bold "命令行工具已就绪。"
fi

# 2) Claude installed and writable without sudo? Auto-open the download page and wait.
if [ ! -d "/Applications/Claude.app" ]; then
  bold "未找到 Claude Desktop,正在打开官方下载页…"
  open "https://claude.ai/download" 2>/dev/null || true
  echo "请下载并把 Claude 拖入「应用程序」。完成后本脚本会自动继续(Ctrl-C 取消)。"
  echo "(为安全起见,本脚本不会替你下载安装这个第三方应用。)"
  while [ ! -d "/Applications/Claude.app" ]; do
    sleep 5; printf '.'
  done
  echo; bold "已检测到 Claude.app。"
fi
# Writability (incl. macOS "App Management" TCC) is diagnosed authoritatively by
# `claude-zh install` itself, which prints exact fix steps — don't second-guess it here.
if [ ! -w "/Applications/Claude.app/Contents" ]; then
  err "Claude.app 不可写(可能属于 root)。请把它拖到「应用程序」重装为你自己的账户,本工具不使用 sudo。"
  pause; exit 1
fi

# 3) Show status + coverage so the user knows what they'll get on THEIR version.
./bin/claude-zh status || true
echo
COV="$(./bin/claude-zh status 2>/dev/null | awk -F'= ' '/Corpus coverage/{print $2}' | awk '{print int($1)}')"
if [ -n "${COV:-}" ] && [ "$COV" -lt 95 ]; then
  err "注意:你这个 Claude 版本比补丁语料新,约 ${COV}% 的界面有中文,其余暂显英文。"
  echo "    可在安装后运行  ./bin/claude-zh translate  用 Claude 补翻剩余部分(需 claude CLI 或 API)。"
  echo
fi

read -r -p "回车开始安装(会退出并替换 Claude.app,原版自动备份);Ctrl-C 取消… " _
echo

# 4) Install and relaunch.
if ./bin/claude-zh install --launch; then
  echo
  bold "完成。"
  echo "• 若界面未自动切换:Claude 左下角头像菜单 → Language → 简体中文。"
  echo "• ⚠️  请确认 Cowork 工作区仍能启动;若异常,双击 uninstall.command 一键回滚。"
  echo "• 想让 Claude 更新后自动保持中文,再运行:  ./bin/claude-zh autopatch install"
else
  err "安装未完成。可双击 uninstall.command 恢复原版,或把上面的报错发我。"
fi
pause
