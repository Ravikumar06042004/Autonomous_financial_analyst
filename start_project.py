import os
import subprocess
import sys
import time


ROOT = os.path.dirname(os.path.abspath(__file__))


def start_process(command, name):
    print(f"Starting {name}...")
    return {
        "name": name,
        "process": subprocess.Popen(
            command,
            cwd=ROOT,
        ),
    }


def stop_processes(processes):
    for item in processes:
        process = item["process"]

        if process.poll() is None:
            print(f"Stopping {item['name']}...")
            process.terminate()

    time.sleep(1)

    for item in processes:
        process = item["process"]

        if process.poll() is None:
            process.kill()


def main():
    processes = []

    commands = [
        (
            [
                sys.executable,
                "manage.py",
                "runserver",
                "8001",
                "--noreload",
            ],
            "Django Dashboard",
        ),
        (
            [
                sys.executable,
                "-m",
                "uvicorn",
                "api.main:app",
                "--port",
                "8000",
            ],
            "FastAPI",
        ),
        (
            [
                sys.executable,
                "-m",
                "scheduler.runner",
            ],
            "Scheduler",
        ),
    ]

    try:
        for command, name in commands:
            item = start_process(command, name)
            processes.append(item)
            time.sleep(2)

            if item["process"].poll() is not None:
                raise RuntimeError(
                    f"{name} failed to start. "
                    "Check the error shown above."
                )

        print()
        print("=" * 60)
        print("AUTONOMOUS FINANCIAL INTELLIGENCE")
        print("=" * 60)
        print("Django    : http://127.0.0.1:8001/")
        print("FastAPI   : http://127.0.0.1:8000/docs")
        print("Scheduler : Running")
        print("=" * 60)
        print("Press Ctrl+C to stop all services.")
        print()

        while True:
            for item in processes:
                if item["process"].poll() is not None:
                    raise RuntimeError(
                        f"{item['name']} stopped unexpectedly."
                    )

            time.sleep(2)

    except KeyboardInterrupt:
        print("\nStopping project...")

    except Exception as exc:
        print(f"\nPROJECT STARTUP FAILED: {exc}")

    finally:
        stop_processes(processes)
        print("All services stopped.")


if __name__ == "__main__":
    main()