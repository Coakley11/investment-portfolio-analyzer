"""Find duplicate Streamlit widget keys in the repo."""
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
keys: dict[str, list[str]] = defaultdict(list)
pattern = re.compile(r"""key\s*=\s*["']([^"']+)["']""")

for path in ROOT.rglob("*.py"):
    if any(x in path.parts for x in (".git", "__pycache__", "scripts")):
        continue
    text = path.read_text(encoding="utf-8")
    for match in pattern.finditer(text):
        keys[match.group(1)].append(str(path.relative_to(ROOT)))

dups = {k: v for k, v in keys.items() if len(v) > 1}
print(f"Total keys: {len(keys)}, duplicates: {len(dups)}")
for k in sorted(dups):
    print(f"\n{k} ({len(dups[k])}x):")
    for loc in dups[k]:
        print(f"  - {loc}")
