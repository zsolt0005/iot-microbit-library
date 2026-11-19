"""Upload library files to a micro:bit, optionally minified.

Minifying removes comments and docstrings and uses one space per indentation
level. The micro:bit stores .py files as text in a ~20 kB file system, so this
saves flash space; RAM use after import does not change.

Usage (from the microbit/ folder):
    uv run python tools/upload.py wifi.py http.py            # minified
    uv run python tools/upload.py --plain wifi.py            # as is
    uv run python tools/upload.py --size *.py                # only print sizes
    uv run python tools/upload.py bench.py:main.py           # upload under another name
"""
import ast
import glob
import sys
import time

import serial


def minify(source):
    """Return source without comments and docstrings, indented with one space."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
    lines = []
    for line in ast.unparse(tree).splitlines():
        stripped = line.lstrip(" ")
        lines.append(" " * ((len(line) - len(stripped)) // 4) + stripped)
    return "\n".join(lines) + "\n"


def find_port():
    ports = glob.glob("/dev/cu.usbmodem*") + glob.glob("/dev/ttyACM*")
    if not ports:
        sys.exit("micro:bit not found - is it connected over USB?")
    return ports[0]


def raw_exec(s, code, timeout=5.0):
    s.write(code.encode() + b"\x04")
    buf = b""
    end = time.time() + timeout
    while time.time() < end and buf.count(b"\x04") < 2:
        buf += s.read_all() or b""
        time.sleep(0.02)
    if not buf.startswith(b"OK"):
        raise RuntimeError("raw REPL did not accept the code: %r" % buf[:80])
    out, _, err = buf[2:].partition(b"\x04")
    err = err.rstrip(b"\x04>")
    if err:
        raise RuntimeError(err.decode(errors="replace"))
    return out.decode(errors="replace")


def upload(files, plain):
    s = serial.Serial(find_port(), 115200, timeout=0.1)
    for _ in range(5):  # stop main.py
        s.write(b"\x03")
        time.sleep(0.1)
    s.write(b"\r\x01")  # raw REPL
    time.sleep(0.5)
    if b"raw REPL" not in s.read_all():
        sys.exit("could not enter the micro:bit REPL")
    for item in files:
        local, _, remote = item.partition(":")
        remote = remote or local.rsplit("/", 1)[-1]
        text = open(local, encoding="utf-8").read()
        data = (text if plain else minify(text)).encode()
        raw_exec(s, "f=open(%r,'wb')" % remote)
        for i in range(0, len(data), 128):
            raw_exec(s, "f.write(%r)" % data[i:i + 128])
        raw_exec(s, "f.close()")
        size = int(raw_exec(s, "import os;print(os.size(%r))" % remote))
        if size != len(data):
            sys.exit("%s: size mismatch %d != %d" % (remote, size, len(data)))
        print("%-16s %6d B -> %6d B" % (remote, len(text.encode()), size))
    s.write(b"\x02")  # back to the normal REPL


def main():
    args = sys.argv[1:]
    plain = "--plain" in args
    only_size = "--size" in args
    files = [a for a in args if not a.startswith("--")]
    if not files:
        sys.exit(__doc__)
    if only_size:
        for f in files:
            text = open(f.partition(":")[0], encoding="utf-8").read()
            print("%-16s %6d B -> %6d B" % (f, len(text.encode()), len(minify(text).encode())))
        return
    upload(files, plain)


main()
