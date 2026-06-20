# PyInstaller spec for the GuardianNode backend (Windows service payload).
# Build on Windows:  pyinstaller --noconfirm guardiannode_backend.spec
# Output: dist/GuardianNodeBackend/GuardianNodeBackend.exe + _internal/
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = (
    collect_submodules("app")
    + collect_submodules("uvicorn")
    + [
        "argon2",
        "pydantic_settings",
        "zeroconf",
        "PIL",
        "ulid",
    ]
)

datas = [
    ("app/prompts", "app/prompts"),
    ("app/data", "app/data"),
    ("app/static", "app/static"),
]

a = Analysis(
    ["pyinstaller_entry.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GuardianNodeBackend",
    console=True,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="GuardianNodeBackend",
)
