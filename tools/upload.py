"""Upload a program and the local modules it imports to a micro:bit, minified.

The program is uploaded as main.py (the file the micro:bit runs after start-up).
Its imports are found in the code, recursively; modules built into the firmware
(microbit, utime, ...) are not files here, so they are skipped. Before uploading,
.py files on the micro:bit that the program does not need are deleted; other files
(data written by the node) are kept.

Minifying removes comments and docstrings and uses one space per indentation
level. The micro:bit stores .py files as text in a ~20 kB file system, so this
saves flash space; RAM use after import does not change.

Usage (from the microbit/ folder):
    uv run python tools/upload.py              # main.py and its imports
    uv run python tools/upload.py bench.py     # bench.py as main.py and its imports
    uv run python tools/upload.py --plain      # as is, not minified
    uv run python tools/upload.py --size       # only print the files and sizes
"""

import ast
import glob
import os
import sys
import time

import serial


def minify(source):
    """Return source without comments and docstrings, indented with one space."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                node.body = body[1:] or [ast.Pass()]
    lines = []
    for line in ast.unparse(tree).splitlines():
        stripped = line.lstrip(" ")
        if stripped:  # ast.unparse adds blank lines between definitions
            lines.append(" " * ((len(line) - len(stripped)) // 4) + stripped)
    return "\n".join(lines) + "\n"


FS_SIZE = 20096  # measured: bytes of .py text that fit into the micro:bit file system


def imports(source):
    """Names of all modules imported anywhere in source (also inside functions and try)."""
    names = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.append(node.module)
    return names


def deps(entry):
    """entry and the local modules it needs, recursively: [(local path, name on micro:bit)]."""
    folder = os.path.dirname(entry)
    found, todo = {entry: "main.py"}, [entry]
    while todo:
        for name in imports(open(todo.pop(), encoding="utf-8").read()):
            path = os.path.join(folder, name + ".py")
            if os.path.exists(path) and path not in found and name != "main":
                found[path] = name + ".py"
                todo.append(path)
    entry_item = [(entry, "main.py")]
    return sorted((p, r) for p, r in found.items() if p != entry) + entry_item


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
    keep = [remote for _, remote in files]
    on_device = raw_exec(s, "import os;print(' '.join(os.listdir()))").split()
    for name in on_device:
        if name.endswith(".py") and name not in keep:
            raw_exec(s, "os.remove(%r)" % name)
            print("%-16s deleted" % name)
    for local, remote in files:
        text = open(local, encoding="utf-8").read()
        data = (text if plain else minify(text)).encode()
        raw_exec(s, "f=open(%r,'wb')" % remote)
        for i in range(0, len(data), 128):
            raw_exec(s, "f.write(%r)" % data[i : i + 128])
        raw_exec(s, "f.close()")
        size = int(raw_exec(s, "print(os.size(%r))" % remote))
        if size != len(data):
            sys.exit("%s: size mismatch %d != %d" % (remote, size, len(data)))
        print("%-16s %6d B -> %6d B" % (remote, len(text.encode()), size))
    s.write(b"\x02")  # back to the normal REPL


def main():
    args = sys.argv[1:]
    plain = "--plain" in args
    names = [a for a in args if not a.startswith("--")]
    entry = names[0] if names else "main.py"
    if len(names) > 1 or not os.path.exists(entry):
        sys.exit(__doc__)
    files = deps(entry)
    used = [n for local, _ in files for n in imports(open(local, encoding="utf-8").read())]
    if "config" in used and not os.path.exists(os.path.join(os.path.dirname(entry), "config.py")):
        sys.exit("config.py is missing - copy config.example.py and fill in your values")
    total = 0
    for local, _ in files:
        text = open(local, encoding="utf-8").read()
        total += len((text if plain else minify(text)).encode())
    print("%d files, %d B of ~%d B" % (len(files), total, FS_SIZE))
    if total > FS_SIZE:
        sys.exit("does not fit into the micro:bit file system")
    if "--size" in args:
        for local, remote in files:
            text = open(local, encoding="utf-8").read()
            print("%-16s %6d B -> %6d B" % (remote, len(text.encode()), len(minify(text).encode())))
        return
    upload(files, plain)


if __name__ == "__main__":
    main()
