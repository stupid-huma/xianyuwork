from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start Xianyu photo workflow bot and worker.",
    )

    parser.add_argument(
        "--no-bot",
        action="store_true",
        help="不启动 Telegram Bot，只启动 worker。",
    )

    parser.add_argument(
        "--no-worker",
        action="store_true",
        help="不启动 worker，只启动 Telegram Bot。",
    )

    parser.add_argument(
        "--worker-once",
        action="store_true",
        help="worker 只运行一次，等价于 python run_worker.py --once。",
    )

    parser.add_argument(
        "--worker-no-telegram",
        action="store_true",
        help="worker 不发送 Telegram 通知，等价于 python run_worker.py --no-telegram。",
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        help="传给 run_worker.py 的日志等级。",
    )

    return parser.parse_args()


def start_process(name: str, script_name: str, extra_args: list[str] | None = None) -> subprocess.Popen:
    """
    启动一个子进程。

    使用 sys.executable 可以保证：
    - 你在 PyCharm 虚拟环境里运行 run.py，就会用同一个虚拟环境的 Python
    - 你在命令行激活 .venv 后运行 run.py，也会用 .venv 的 Python
    """
    extra_args = extra_args or []

    command = [
        sys.executable,
        script_name,
        *extra_args,
    ]

    print()
    print(f"🚀 Starting {name}:")
    print(" ".join(command))
    print()

    return subprocess.Popen(
        command,
        cwd=PROJECT_ROOT,
    )


def stop_processes(processes: dict[str, subprocess.Popen]) -> None:
    """
    停止所有子进程。
    """
    print()
    print("🛑 Stopping processes...")
    print()

    for name, process in processes.items():
        if process.poll() is None:
            print(f"Stopping {name}...")
            process.terminate()

    deadline = time.time() + 10

    for name, process in processes.items():
        while process.poll() is None and time.time() < deadline:
            time.sleep(0.2)

        if process.poll() is None:
            print(f"Force killing {name}...")
            process.kill()

    print()
    print("✅ All processes stopped.")
    print()


def main() -> None:
    args = parse_args()

    if args.no_bot and args.no_worker:
        print("⚠️ 你同时指定了 --no-bot 和 --no-worker，没有需要启动的进程。")
        return

    processes: dict[str, subprocess.Popen] = {}

    try:
        if not args.no_bot:
            processes["bot"] = start_process(
                name="Telegram Bot",
                script_name="run_bot.py",
            )

        if not args.no_worker:
            worker_args: list[str] = []

            # 你已经把 run_worker.py 的默认 mode 改成 both，
            # 所以这里不需要再传 --mode both。
            if args.worker_once:
                worker_args.append("--once")

            if args.worker_no_telegram:
                worker_args.append("--no-telegram")

            if args.log_level:
                worker_args.extend(["--log-level", args.log_level])

            processes["worker"] = start_process(
                name="Worker",
                script_name="run_worker.py",
                extra_args=worker_args,
            )

        print()
        print("✅ System started.")
        print("按 Ctrl + C 可以同时停止 Bot 和 Worker。")
        print()

        while True:
            time.sleep(1)

            for name, process in processes.items():
                return_code = process.poll()

                if return_code is not None:
                    print()
                    print(f"⚠️ Process exited: {name}, return code = {return_code}")
                    print("为了避免只剩一个进程继续运行，现在停止全部进程。")
                    stop_processes(processes)
                    raise SystemExit(return_code)

    except KeyboardInterrupt:
        stop_processes(processes)


if __name__ == "__main__":
    main()