#!/usr/bin/env python3
"""Register or remove the lolsync:// protocol for one-click bridge startup.

The handler only runs start_lcu_server.py with a fixed path; it does not pass
URL arguments to a shell. Registration is per-user (HKCU) and reversible.
"""

import argparse
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
START = BASE / "scripts" / "start_lcu_server.py"
PROTOCOL = "lolsync"
KEY_PATH = rf"Software\Classes\{PROTOCOL}"


def pythonw_path():
    candidate = Path(sys.executable).with_name("pythonw.exe")
    return candidate if candidate.is_file() else Path(sys.executable)


def protocol_command():
    return f'"{pythonw_path()}" "{START}"'


def install():
    import winreg

    command = protocol_command()
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY_PATH) as key:
        winreg.SetValueEx(key, None, 0, winreg.REG_SZ, "URL:LoL Sync Bridge")
        winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY_PATH + r"\shell\open\command") as key:
        winreg.SetValueEx(key, None, 0, winreg.REG_SZ, command)
    print(f"已注册 {PROTOCOL}:// -> {command}")
    print("首次点击网站按钮时浏览器会询问是否打开 “LoL Sync”，选择允许即可。")
    print("撤销：python scripts/install_protocol.py --remove")


def remove():
    import winreg

    def delete_tree(path):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_ALL_ACCESS) as key:
                while True:
                    try:
                        child = winreg.EnumKey(key, 0)
                    except OSError:
                        break
                    delete_tree(path + "\\" + child)
        except FileNotFoundError:
            return
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)

    delete_tree(KEY_PATH)
    print(f"已移除 {PROTOCOL}:// 协议")


def status():
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, KEY_PATH + r"\shell\open\command", 0, winreg.KEY_READ,
        ) as key:
            value, _ = winreg.QueryValueEx(key, None)
    except FileNotFoundError:
        print(f"{PROTOCOL}:// 未注册")
        return 1
    print(f"{PROTOCOL}:// -> {value}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="注册/移除 lolsync:// 一键启动协议。")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--remove", action="store_true", help="移除协议注册")
    group.add_argument("--status", action="store_true", help="查看当前注册命令")
    args = parser.parse_args(argv)

    if sys.platform != "win32":
        print("该协议注册仅支持 Windows。")
        return 2
    if not START.is_file():
        print(f"找不到启动脚本：{START}")
        return 2

    if args.remove:
        remove()
        return 0
    if args.status:
        return status()
    install()
    return 0


if __name__ == "__main__":
    sys.exit(main())
