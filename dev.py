#!/usr/bin/env python3
"""
Development server script that runs both Django and Tailwind CSS watch processes.
Usage: python dev.py
"""

import subprocess
import time
from pathlib import Path


def run_command(command, cwd=None):
    """Run a command in the background and return the process."""
    return subprocess.Popen(
        command,
        shell=True,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1,
    )


def main():
    print("🚀 Starting Newsflow development environment...")

    # Get the project root directory
    project_root = Path(__file__).parent

    processes = []

    try:
        # Start Tailwind CSS watch process
        print("📦 Starting Tailwind CSS watcher...")
        tailwind_process = run_command("npm run dev-css", cwd=project_root)
        processes.append(("Tailwind CSS", tailwind_process))

        # Give Tailwind a moment to start
        time.sleep(2)

        # Start Django development server
        print("🌐 Starting Django development server...")
        django_process = run_command(
            "uv run python manage.py runserver",
            cwd=project_root,
        )
        processes.append(("Django Server", django_process))

        print("\n✅ Development environment is ready!")
        print("🎨 Tailwind CSS: Watching for changes and hot-reloading")
        print("🖥️  Django Server: http://127.0.0.1:8000")
        print(
            "\n📝 Make changes to your templates or CSS - they'll update automatically!",
        )
        print("Press Ctrl+C to stop all processes.\n")

        # Monitor processes
        while True:
            for name, process in processes:
                if process.poll() is not None:
                    print(f"❌ {name} has stopped unexpectedly")
                    return
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n🛑 Shutting down development environment...")

        # Terminate all processes
        for name, process in processes:
            try:
                process.terminate()
                process.wait(timeout=5)
                print(f"✅ {name} stopped")
            except subprocess.TimeoutExpired:
                process.kill()
                print(f"🔪 {name} force killed")
            except Exception as e:
                print(f"❌ Error stopping {name}: {e}")

        print("👋 Development environment stopped")


if __name__ == "__main__":
    main()
