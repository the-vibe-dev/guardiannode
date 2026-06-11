# PyInstaller spec for the GuardianNode child-device agent.
# Build on Windows:  pyinstaller --noconfirm guardiannode_agent.spec
# Output: dist/GuardianNodeAgent/ containing GuardianNodeAgent.exe,
# GuardianNodeTray.exe, GuardianNodeWatchdog.exe and one shared _internal/.
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules("src") + [
    "zeroconf",
    "PIL",
    "pystray",
    "mss",
    "httpx",
]

datas = [
    ("policies", "policies"),
    ("ocr_regions", "ocr_regions"),
]


def make_analysis(script):
    return Analysis(
        [script],
        pathex=["."],
        binaries=[],
        datas=datas,
        hiddenimports=hiddenimports,
        excludes=["tkinter"],
    )


a_agent = make_analysis("entry_agent.py")
a_tray = make_analysis("entry_tray.py")
a_watchdog = make_analysis("entry_watchdog.py")

MERGE(
    (a_agent, "GuardianNodeAgent", "GuardianNodeAgent"),
    (a_tray, "GuardianNodeTray", "GuardianNodeTray"),
    (a_watchdog, "GuardianNodeWatchdog", "GuardianNodeWatchdog"),
)

pyz_agent = PYZ(a_agent.pure)
pyz_tray = PYZ(a_tray.pure)
pyz_watchdog = PYZ(a_watchdog.pure)

exe_agent = EXE(
    pyz_agent, a_agent.scripts, [],
    exclude_binaries=True, name="GuardianNodeAgent", console=True, icon=None,
)
exe_tray = EXE(
    pyz_tray, a_tray.scripts, [],
    # The tray app is the child-visible surface; no console window.
    exclude_binaries=True, name="GuardianNodeTray", console=False, icon=None,
)
exe_watchdog = EXE(
    pyz_watchdog, a_watchdog.scripts, [],
    exclude_binaries=True, name="GuardianNodeWatchdog", console=True, icon=None,
)

coll = COLLECT(
    exe_agent, a_agent.binaries, a_agent.datas,
    exe_tray, a_tray.binaries, a_tray.datas,
    exe_watchdog, a_watchdog.binaries, a_watchdog.datas,
    name="GuardianNodeAgent",
)
