import os
import subprocess
import sys

PROJ = r"D:\Phineas\Synapse"
WIN_PYTHON = os.environ.get("SYNAPSE_PYTHON", sys.executable)
ISCC = r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
DIST_EXE = os.path.join(PROJ, "dist", "Synapse", "Synapse.exe")
INSTALLER_SCRIPT = os.path.join(PROJ, "installer.iss")
OUTPUT_EXE = os.path.join(PROJ, "installer_output", "Synapse_Setup_v1.0.0.exe")
WEB_RELEASE_SCRIPT = os.path.join(PROJ, "build_release_web.py")


def run(cmd):
    result = subprocess.run(cmd, cwd=PROJ, text=True, capture_output=True)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        sys.exit(result.returncode)
    return result


if not os.path.exists(ISCC):
    print("Inno Setup compiler not found: {}".format(ISCC))
    sys.exit(1)

print("Building Synapse app...")
run([WIN_PYTHON, os.path.join(PROJ, "build_final.py"), "--no-start"])

if not os.path.exists(DIST_EXE):
    print("Missing app exe: {}".format(DIST_EXE))
    sys.exit(1)

print("Building installer...")
run([ISCC, INSTALLER_SCRIPT])

print("Installer OK: {}".format(OUTPUT_EXE))

if "--skip-web" not in sys.argv:
    print("Building download site...")
    run([WIN_PYTHON, WEB_RELEASE_SCRIPT, "--skip-installer"])
