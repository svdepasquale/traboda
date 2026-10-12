#!/usr/bin/env python3
"""Smoke tests: every module compiles for the badge, every app survives the simulator.

  python3 tests/smoke.py [--micropython PATH] [--mpy-cross PATH] [--keep]

For each app in the launcher registry and each game, it runs the steps in
sim/scenarios/<name>.txt (one steps string per line, # comments) or a default walk
(open, move around, select, back), and fails on a Python traceback or an "Errore in"
dialog. Screenshots land in a temporary folder (kept with --keep, for a look).
"""

import argparse
import ast
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_WALK = "wait:900,snap:open,key:down,key:down,key:A,wait:600,snap:select,hold:A,wait:400,hold:A,wait:400,snap:back"


def registry():
    def tuples(path, name):
        tree = ast.parse(open(path).read())
        for node in tree.body:
            if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == name:
                return ast.literal_eval(node.value)
        return ()

    apps = [a[0] for a in tuples(os.path.join(ROOT, "src/traboda/apps/__init__.py"), "APPS")]
    games = [g[0] for g in tuples(os.path.join(ROOT, "src/traboda/apps/games/__init__.py"), "GAMES")]
    return apps, games


def scenarios(name):
    path = os.path.join(ROOT, "sim", "scenarios", name + ".txt")
    if not os.path.exists(path):
        return [DEFAULT_WALK]
    lines = [ln.strip() for ln in open(path) if ln.strip() and not ln.strip().startswith("#")]
    return lines or [DEFAULT_WALK]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--micropython", default=shutil.which("micropython") or "micropython")
    ap.add_argument("--mpy-cross", default=os.path.join(
        ROOT, "firmware/.build/micropython/mpy-cross/build/mpy-cross"))
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    failures = []

    if os.path.exists(args.mpy_cross):
        for path in sorted(glob.glob(os.path.join(ROOT, "src/traboda/**/*.py"), recursive=True)):
            r = subprocess.run([args.mpy_cross, "-march=xtensawin", "-o", os.devnull, path],
                               capture_output=True, text=True)
            if r.returncode:
                failures.append("compile %s: %s" % (os.path.relpath(path, ROOT), r.stderr.strip()))
        print("mpy-cross: %d failure(s)" % len(failures))
    else:
        print("mpy-cross not found, skipping the compile check")

    out_root = tempfile.mkdtemp(prefix="traboda-smoke-")
    apps, games = registry()
    runs = [(a, "app:%s," % a) for a in apps if a != "games"]
    runs += [("games/" + g, "app:games,wait:500,%s" % ("key:down," * i) + "key:A,wait:400,")
             for i, g in enumerate(games)]
    for name, prefix in runs:
        short = name.split("/")[-1]
        for n, steps in enumerate(scenarios(short)):
            if steps.startswith("app:"):
                steps = steps.split(",", 1)[1] if "," in steps else ""
            out = os.path.join(out_root, short.replace("/", "_") + "-%d" % n)
            r = subprocess.run([args.micropython, os.path.join(ROOT, "sim/run.py"), out, prefix + steps],
                               capture_output=True, text=True, cwd=ROOT, timeout=300)
            text = r.stdout + r.stderr
            bad = "Traceback" in text or "Errore in" in text or r.returncode != 0
            if bad:
                tail = "\n".join(text.strip().splitlines()[-12:])
                failures.append("%s scenario %d:\n%s" % (name, n, tail))
            print("%-18s #%d %s" % (name, n, "FAIL" if bad else "ok"))

    if args.keep:
        print("screenshots: python3 sim/topng.py <dir> under", out_root)
    else:
        shutil.rmtree(out_root, ignore_errors=True)
    if failures:
        print("\n%d failure(s):\n" % len(failures) + "\n\n".join(failures))
        sys.exit(1)
    print("all good")


if __name__ == "__main__":
    main()
