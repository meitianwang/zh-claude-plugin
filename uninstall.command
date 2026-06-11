#!/bin/bash
# Double-click entry point: restore the original Claude.app from the latest backup.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==== 卸载 Claude 中文补丁（恢复原版）===="
echo
read -r -p "回车开始恢复最近一次备份；Ctrl-C 取消… " _

# Also remove the auto-reapply agent if present, so it doesn't re-patch.
"$DIR/bin/claude-zh" autopatch uninstall || true
"$DIR/bin/claude-zh" uninstall --launch

echo
read -r -p "按回车退出… " _
