"""`open()` on a file that does not exist must raise, catchably, exactly as
CPython's does.

A bare `fopen()` returns NULL on a missing file and py2c's lowering of
`open(...)`/`with open(...) as f:` never checked that -- no exception ever
reached an `except IOError:` around it, so a "try each candidate directory,
first one that opens wins" loop (the shape `tools/cpprust.py` uses to find
a header under `--basedir`/`--incdir`) took the very first candidate
whether or not it actually existed, reading an empty string from the NULL
FILE* silently. Real-world impact: every `#include "x.h"` in the litehtml
corpus resolved to a nonexistent path in the transpiled native binary, so
no header was ever spliced in, while the CPython build (where `open()`
does raise) worked correctly.
"""
import os


def try_open(path):
    try:
        with open(path, "r") as f:
            return f.read()
    except IOError:
        return None


def find_first(paths):
    for p in paths:
        try:
            with open(p, "r") as f:
                data = f.read()
            return p, data
        except IOError:
            continue
    return None, None


def main():
    missing = "/nonexistent/definitely/not/a/real/file/py2c_test.txt"
    print("missing_is_none " + str(try_open(missing) is None))

    real = "_test_open_missing_tmpfile.txt"
    with open(real, "w") as f:
        f.write("hello")
    got = try_open(real)
    print("real_is_none " + str(got is None))
    print("real_content " + str(got))

    cand, data = find_first([missing, real])
    print("cand_is_missing " + str(cand == missing))
    print("cand_is_real " + str(cand == real))
    print("data " + str(data))

    os.remove(real)
    print("removed_is_none " + str(try_open(real) is None))
    return None


main()
