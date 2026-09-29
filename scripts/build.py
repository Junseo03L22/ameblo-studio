"""Build on the target OS. Windows -> exe folder, macOS -> .app.
Chromium is bundled so recipients do not need Python or playwright install.
"""
from pathlib import Path
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent


def run(*args, env=None):
    subprocess.run([sys.executable, *args], cwd=ROOT, env=env, check=True)


def main():
    env = dict(os.environ)
    browsers = ROOT / ".browsers"
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers)
    run("-m", "playwright", "install", "chromium", env=env)
    licenses = ROOT / "build" / "third-party-licenses"
    licenses.mkdir(parents=True, exist_ok=True)
    inventory = []
    for dist in importlib.metadata.distributions():
        name = dist.metadata.get("Name", "unknown")
        inventory.append({"name": name, "version": dist.version, "license": dist.metadata.get("License-Expression") or dist.metadata.get("License", "See package license")})
        for f in dist.files or []:
            if any(word in f.name.lower() for word in ("license", "copying", "notice")) and str(f).endswith((".txt", ".md", "LICENSE", "COPYING", "NOTICE")):
                source = Path(dist.locate_file(f))
                if source.is_file():
                    destination = licenses / name / str(f).replace("..", "_").replace("/", "_")
                    destination.parent.mkdir(exist_ok=True)
                    shutil.copyfile(source, destination)
    (licenses / "inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2), "utf-8")
    run("-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--onedir",
        "--name", "AmebloStudio", "--collect-all", "playwright",
        "--add-data", str(browsers) + os.pathsep + "browsers",
        "--add-data", str(licenses) + os.pathsep + "third-party-licenses",
        "--add-data", str(ROOT / "LICENSE") + os.pathsep + ".",
        "--add-data", str(ROOT / "THIRD_PARTY.md") + os.pathsep + ".",
        "run_app.py", env=env)
    dist = ROOT / "dist"
    for name in ("README.md", "LICENSE", "THIRD_PARTY.md"):
        shutil.copyfile(ROOT / name, dist / name)
    print("Build complete:", dist)
    print("Windows: share the entire AmebloStudio folder, not only the .exe.")


if __name__ == "__main__":
    main()
