"""工具函数 - 日志美化、时间格式化"""


class _Colors:
    CYAN    = "\033[96m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    RED     = "\033[91m"
    MAGENTA = "\033[95m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RESET   = "\033[0m"

_C = _Colors


def log_step(emoji: str, msg: str) -> None:
    """步骤标题，cyan + bold"""
    print(f"\n{_C.CYAN}{_C.BOLD}{emoji}  {msg}{_C.RESET}")


def log_info(msg: str) -> None:
    """详细信息，dim"""
    print(f"   {_C.DIM}{msg}{_C.RESET}")


def log_success(msg: str) -> None:
    """成功，green"""
    print(f"   {_C.GREEN}✓ {msg}{_C.RESET}")


def log_warn(msg: str) -> None:
    """警告，yellow"""
    print(f"   {_C.YELLOW}⚠ {msg}{_C.RESET}")


def log_error(msg: str) -> None:
    """错误，red"""
    print(f"   {_C.RED}✗ {msg}{_C.RESET}")


def format_time(seconds: float) -> str:
    """格式化为 MM:SS.ss 或 HH:MM:SS.ss"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:05.2f}"
    return f"{m:02d}:{s:05.2f}"
