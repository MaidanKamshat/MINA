"""Run existing baseline offline checks without external API calls or heavy ML downloads."""
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
tests = [
    "complexity_router.py",
    "test_tot_critic.py",
    "test_tot_llm_generator.py",
    "test_tot_constraints_experiment9.py",
    "test_mina_tot_integrated.py",
]
failed = []
for name in tests:
    print(f"\n=== {name} ===", flush=True)
    result = subprocess.run([sys.executable, str(root / name)], cwd=root)
    if result.returncode:
        failed.append(name)
print("\nOFFLINE BASELINE: " + ("PASS" if not failed else "FAIL: " + ", ".join(failed)))
raise SystemExit(bool(failed))
