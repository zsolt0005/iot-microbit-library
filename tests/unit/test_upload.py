"""tools/upload.py: minifying, finding the files a program needs and uploading them.

Uploading runs against a simulated micro:bit: a fake serial port that answers like the
raw REPL and keeps the file system in a dict.
"""

import ast
import builtins
import importlib.util
import os
import types

import pytest

_spec = importlib.util.spec_from_file_location(
    "upload", os.path.join(os.path.dirname(__file__), "..", "..", "tools", "upload.py")
)
upload = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(upload)


# --- minify ---------------------------------------------------------------------------------


def test_minify_removes_docstrings_and_comments():
    src = '''"""Module doc."""
# comment
class A:
    """Class doc."""

    def f(self, x):
        """Function doc."""
        return x + 1  # comment
'''
    out = upload.minify(src)
    assert "doc" not in out and "comment" not in out
    assert out == "class A:\n def f(self, x):\n  return x + 1\n"


def test_minify_keeps_behaviour():
    src = 'def f(n):\n    """Doc."""\n    s = "# not a comment"\n    return [s] * n\n'
    ns_a, ns_b = {}, {}
    exec(src, ns_a)
    exec(upload.minify(src), ns_b)
    assert ns_a["f"](2) == ns_b["f"](2) == ["# not a comment"] * 2


def test_minify_body_with_only_docstring():
    out = upload.minify('def f():\n    """Only a docstring."""\n')
    assert out == "def f():\n pass\n"
    ast.parse(out)


def test_minify_keeps_string_that_is_not_first():
    out = upload.minify('x = 1\n"""not a docstring"""\n')
    assert "not a docstring" in out


# --- imports and deps -----------------------------------------------------------------------


def test_imports_everywhere_in_the_code():
    src = (
        "import a, b.c\nfrom d import e\nfrom . import rel\n"
        "def f():\n    import g\ntry:\n    import h\nexcept ImportError:\n    pass\n"
    )
    assert upload.imports(src) == ["a", "b.c", "d", "g", "h"]  # relative import skipped


@pytest.fixture
def folder(tmp_path):
    def write(name, text):
        (tmp_path / name).write_text(text, encoding="utf-8")

    write("main.py", "import config\nimport wifi, mqtt\nfrom microbit import i2c\nimport main\n")
    write("config.py", "X = 1\n")
    write("wifi.py", "from utime import ticks_ms\n")
    write("mqtt.py", "import wifi\ndef f():\n    from guard import read\n")  # import in a function
    write("guard.py", "try:\n    import ujson\nexcept ImportError:\n    pass\n")
    write("bench.py", "import sonar\nimport missing\n")
    write("sonar.py", "import bench\n")  # cycle back to the program
    write("unused.py", "")
    return tmp_path


def remotes(files):
    return [remote for _, remote in files]


def test_deps_of_main_recursively(folder):
    files = upload.deps(str(folder / "main.py"))
    assert remotes(files) == ["config.py", "guard.py", "mqtt.py", "wifi.py", "main.py"]
    assert files[-1] == (str(folder / "main.py"), "main.py")  # main.py last
    assert "unused.py" not in remotes(files)


def test_other_program_becomes_main_without_imports_of_main(folder):
    files = upload.deps(str(folder / "bench.py"))
    assert files == [(str(folder / "sonar.py"), "sonar.py"), (str(folder / "bench.py"), "main.py")]


def test_deps_of_the_real_library():
    here = os.path.join(os.path.dirname(__file__), "..", "..")
    files = remotes(upload.deps(os.path.join(here, "mqtt.py")))
    assert files == ["wifi.py", "main.py"]  # mqtt.py as the program, wifi.py from its imports


# --- simulated micro:bit --------------------------------------------------------------------


class FakeMicrobit:
    """Serial port of a micro:bit in the raw REPL with a file system in a dict."""

    def __init__(self, files=None, truncate=None, repl=True):
        self.fs = dict(files or {})
        self.truncate = truncate  # file name whose writes are cut short (broken transfer)
        self.repl = repl
        self.out = b""
        self.code = b""
        self.log = []  # executed code
        self._name = None
        self._globals = None  # the REPL keeps variables (os, f) between commands

    # serial.Serial API used by upload.py
    def write(self, data):
        if data == b"\r\x01":
            self.out += b"raw REPL; CTRL-B to exit\r\n>" if self.repl else b""
        elif data in (b"\x03", b"\x02"):
            pass
        else:
            self.code += data
            if self.code.endswith(b"\x04"):
                self._run(self.code[:-1].decode())
                self.code = b""

    def read_all(self):
        out, self.out = self.out, b""
        return out

    # executing the code like MicroPython would
    def _run(self, code):
        self.log.append(code)
        printed = []
        fs = self.fs
        sim = self

        class File:
            def write(self, data):
                if sim._name != sim.truncate:
                    fs[sim._name] += data

            def close(self):
                pass

        def fake_open(name, mode):
            sim._name = name
            fs[name] = b""
            return File()

        fake_os = types.SimpleNamespace(
            listdir=lambda: list(fs), remove=fs.pop, size=lambda name: len(fs[name])
        )

        def fake_import(name, *args):
            return fake_os if name == "os" else builtins.__import__(name, *args)

        if self._globals is None:
            self._globals = {
                "__builtins__": dict(vars(builtins), __import__=fake_import, open=fake_open)
            }
        self._globals["print"] = lambda *a: printed.append(" ".join(str(x) for x in a))
        try:
            exec(code, self._globals)
            err = b""
        except Exception as e:  # noqa: BLE001 - becomes the REPL error output
            err = ("Traceback\r\n%s: %s\r\n" % (type(e).__name__, e)).encode()
        out = "".join(p + "\r\n" for p in printed).encode()
        self.out += b"OK" + out + b"\x04" + err + b"\x04>"


@pytest.fixture
def device(monkeypatch):
    holder = {}

    def connect(files=None, **kwargs):
        dev = FakeMicrobit(files, **kwargs)
        holder["dev"] = dev
        monkeypatch.setattr(upload.serial, "Serial", lambda *a, **k: dev)
        return dev

    monkeypatch.setattr(upload.glob, "glob", lambda p: ["/dev/cu.usbmodem1"] if "cu." in p else [])
    monkeypatch.setattr(upload.time, "sleep", lambda s: None)
    return connect


def test_upload_deletes_old_code_but_keeps_data(device, folder):
    dev = device({"old.py": b"x", "main.py": b"old", "data.txt": b"measurements", "wifi.py": b"w"})
    files = upload.deps(str(folder / "main.py"))
    upload.upload(files, plain=False)
    assert sorted(dev.fs) == ["config.py", "data.txt", "guard.py", "main.py", "mqtt.py", "wifi.py"]
    assert dev.fs["data.txt"] == b"measurements"  # files written by the node stay
    src = (folder / "mqtt.py").read_text(encoding="utf-8")
    assert dev.fs["mqtt.py"] == upload.minify(src).encode()


def test_upload_deletes_before_writing_and_main_is_last(device, folder):
    dev = device({"old.py": b"x"})
    upload.upload(upload.deps(str(folder / "main.py")), plain=False)
    opened = [c for c in dev.log if c.startswith("f=open")]
    assert opened[-1] == "f=open('main.py','wb')"
    assert dev.log.index("os.remove('old.py')") < dev.log.index(opened[0])  # frees space first


def test_upload_plain_and_long_file_in_chunks(device, tmp_path):
    text = "# comment\n" + "x = 1\n" * 100  # 610 B: 5 chunks of 128 B
    (tmp_path / "main.py").write_text(text, encoding="utf-8")
    dev = device()
    upload.upload(upload.deps(str(tmp_path / "main.py")), plain=True)
    assert dev.fs["main.py"] == text.encode()
    assert len([c for c in dev.log if c.startswith("f.write")]) == 5


def test_upload_stops_on_size_mismatch(device, folder):
    device(truncate="wifi.py")
    with pytest.raises(SystemExit, match="wifi.py: size mismatch"):
        upload.upload(upload.deps(str(folder / "main.py")), plain=False)


def test_upload_without_repl(device, folder):
    device(repl=False)
    with pytest.raises(SystemExit, match="REPL"):
        upload.upload(upload.deps(str(folder / "main.py")), plain=False)


def test_device_error_is_reported(device):
    dev = device()
    with pytest.raises(RuntimeError, match="KeyError"):
        upload.raw_exec(dev, "import os;os.size('x')")


def test_no_microbit_connected(monkeypatch):
    monkeypatch.setattr(upload.glob, "glob", lambda p: [])
    with pytest.raises(SystemExit, match="not found"):
        upload.find_port()


def test_port_on_linux(monkeypatch):
    monkeypatch.setattr(upload.glob, "glob", lambda p: ["/dev/ttyACM0"] if "ACM" in p else [])
    assert upload.find_port() == "/dev/ttyACM0"


# --- command line ---------------------------------------------------------------------------


def run(monkeypatch, folder, *args):
    monkeypatch.chdir(folder)
    monkeypatch.setattr(upload.sys, "argv", ["upload.py", *args])
    calls = []
    monkeypatch.setattr(upload, "upload", lambda files, plain: calls.append((files, plain)))
    upload.main()
    return calls


def test_cli_default_is_main(monkeypatch, folder, capsys):
    calls = run(monkeypatch, folder)
    files, plain = calls[0]
    assert remotes(files)[-1] == "main.py" and plain is False
    assert capsys.readouterr().out.startswith("5 files, ")


def test_cli_other_program_and_plain(monkeypatch, folder):
    (files, plain) = run(monkeypatch, folder, "bench.py", "--plain")[0]
    assert files == [("sonar.py", "sonar.py"), ("bench.py", "main.py")] and plain is True


def test_cli_size_does_not_upload(monkeypatch, folder, capsys):
    assert run(monkeypatch, folder, "--size") == []
    out = capsys.readouterr().out
    assert "mqtt.py" in out and "main.py" in out and "unused.py" not in out


def test_cli_missing_config(monkeypatch, folder):
    (folder / "config.py").unlink()
    with pytest.raises(SystemExit, match="config.example.py"):
        run(monkeypatch, folder)


def test_cli_too_big(monkeypatch, folder):
    (folder / "wifi.py").write_text("x = %r\n" % ("a" * 21000), encoding="utf-8")
    with pytest.raises(SystemExit, match="does not fit"):
        run(monkeypatch, folder)


@pytest.mark.parametrize("args", [("nothing.py",), ("main.py", "bench.py")])
def test_cli_usage(monkeypatch, folder, args):
    with pytest.raises(SystemExit, match="Usage"):
        run(monkeypatch, folder, *args)
