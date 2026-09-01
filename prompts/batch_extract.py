"""批量跑 _extract_ships.py 1..13 →写 prompts/extract_ships_Chapter_*.md"""
import subprocess
from pathlib import Path

ROOT = Path("D:/天黑之前/Novel_New")
PY = "D:/Python/python.exe"
SCRIPT = ROOT / "engine" / "_extract_ships.py"
OUT_DIR = ROOT / "prompts"
OUT_DIR.mkdir(exist_ok=True)

for n in range(1, 14):
    out = OUT_DIR / f"extract_ships_Chapter_{n:02d}.md"
    # Python on Windows 输出 GBK（不是 UTF-8）
    result = subprocess.run(
        [PY, str(SCRIPT), str(n)],
        capture_output=True
    )
    if result.returncode == 0:
        # 用 GBK 解码 stdout（Windows 中文 console 默认编码）
        try:
            text = result.stdout.decode("gbk")
        except UnicodeDecodeError:
            text = result.stdout.decode("utf-8", errors="replace")
        out.write_text(text, encoding="utf-8")
        print(f"[OK] ch{n:02d} -> {out.name} ({len(text)} chars)")
    else:
        print(f"[FAIL] ch{n:02d}: {result.stderr[:200]}")