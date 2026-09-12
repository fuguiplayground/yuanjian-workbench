#!/bin/bash
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  echo "请在 Codex 中打开此文件夹，让它按 README.md 查找 Python 并启动工作台。"
  read -r reply
  exit 1
fi
echo "远见工作台正在启动。使用期间请保留此终端窗口，关闭窗口即停止服务。"
python3 "team_start.py" --open --project caaaa93ac46840cb "$@"
result=$?
if [ "$result" -ne 0 ]; then
  echo "工作台未能启动，请保留上方提示。按回车关闭。"
  read -r reply
fi
exit "$result"
