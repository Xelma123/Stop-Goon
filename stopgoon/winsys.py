"""Windows registry + WinINET helpers (PRD §7.1, §7.2).

Only AutoConfigURL is ever touched; ProxyServer/ProxyEnable never are.

Manual CLI until install.py exists (run from the repo root):
    py -m stopgoon.winsys show
    py -m stopgoon.winsys set <version>
    py -m stopgoon.winsys clear
"""

import ctypes
import re
import sys
import winreg

INTERNET_SETTINGS = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
_OURS_RE = re.compile(r"^http://127\.0\.0\.1:\d+/stopgoon\.pac(\?.*)?$")
INTERNET_OPTION_REFRESH = 37
INTERNET_OPTION_SETTINGS_CHANGED = 39


def get_autoconfig_url() -> str | None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS) as key:
        try:
            value, _ = winreg.QueryValueEx(key, "AutoConfigURL")
        except FileNotFoundError:
            return None
    return value or None


def pac_url(port: int, version: str) -> str:
    return f"http://127.0.0.1:{port}/stopgoon.pac?v={version}"


def is_ours(url: str | None) -> bool:
    return bool(url) and _OURS_RE.match(url) is not None


def set_autoconfig_url(url: str) -> None:
    """Write AutoConfigURL. Refuses to overwrite a value that is not ours."""
    current = get_autoconfig_url()
    if current and not is_ours(current):
        raise PermissionError(current)
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS, 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(key, "AutoConfigURL", 0, winreg.REG_SZ, url)
    notify_settings_changed()


def clear_autoconfig_url() -> bool:
    """Delete AutoConfigURL only if it is ours. Returns True if deleted."""
    if not is_ours(get_autoconfig_url()):
        return False
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS, 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.DeleteValue(key, "AutoConfigURL")
    notify_settings_changed()
    return True


def notify_settings_changed() -> None:
    fn = ctypes.windll.wininet.InternetSetOptionW
    fn.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong]
    fn.restype = ctypes.c_int
    fn(None, INTERNET_OPTION_SETTINGS_CHANGED, None, 0)
    fn(None, INTERNET_OPTION_REFRESH, None, 0)


def _main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "show"
    if cmd == "show":
        print(f"AutoConfigURL: {get_autoconfig_url() or '(yok)'}")
    elif cmd == "set" and len(argv) == 2:
        url = pac_url(8898, argv[1])
        try:
            set_autoconfig_url(url)
        except PermissionError as e:
            print(f"Mevcut bir AutoConfigURL var, üzerine yazılmadı: {e}")
            return 1
        print(f"AutoConfigURL ayarlandı: {url}")
    elif cmd == "clear":
        if clear_autoconfig_url():
            print("AutoConfigURL silindi.")
        else:
            print("AutoConfigURL Stop Goon'a ait değil veya yok; dokunulmadı.")
    else:
        print("Kullanım: py -m stopgoon.winsys show | set <sürüm> | clear")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
