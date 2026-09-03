"""A `re.compile(pattern, re.MULTILINE)` flags argument is silently dropped:
py2c's regex pre-pass interns only `node.args[0]` (the pattern text) from a
`re.compile(...)` call, never looking at a second argument, and
`crust_re_compile` itself has no multiline mode to opt into either (its own
docs list "inline flags" -- `(?m)` and friends -- as an unsupported,
compile-error feature, not a silently-ignored one; a *Python-level* flags
argument is not even inline, so nothing rejects it -- it just never reaches
the engine). So `^`/`$` in a pattern built with `re.M` compile as plain
*string* anchors: `^` matches only literal offset 0, not the start of every
line -- correct only for a subject that happens to be one line, or whose
first `^` is truly at offset 0. Against real multi-line text (a source file
with a comment before the first matching line, for instance) the pattern
matches only at the very start, or not at all, while CPython's `re.M`
matches at every line boundary.

`tools/cpprust.py` hit exactly this: `_ANY_INCLUDE`, used to splice a
`#include`d header's declarations into the same translation unit, was
`re.compile(..., re.MULTILINE)` -- and never matched a single `#include` in
the native binary, because no real source file has one at literal offset
0. `_expand_headers` silently spliced nothing, so a class declared in a
header and defined in its .cpp never came together, everywhere.

The fix used there, and the one this test pins, is not new engine support:
it is CPython's own recipe for a portable `re.M`-free anchor -- `(?<![^\n])`
for `^` and `(?![^\n])` for `$`, fixed-width lookaround the engine already
supports -- which matches at every line boundary under both CPython and
py2c, with no flags argument to be dropped.
"""
import re

# The bug, still reproduced here for the record: a `re.M`-flagged pattern
# whose `^` never matches past offset 0 in the native binary. `_check`
# below never calls this one -- only the workaround is asserted to behave
# correctly -- but it stays compiled so a future engine change that quietly
# starts honoring `re.M` does not leave this file's own claim unverified;
# see the last two lines of `main`.
_BROKEN_M = re.compile(r'^X(\d+)$', re.MULTILINE)

# The fix: the same anchors, spelled as fixed-width lookaround instead of
# relying on a flags argument py2c does not read.
_FIXED = re.compile(r'(?<![^\n])X(\d+)(?![^\n])')


def main():
    text = "one\nX1\ntwo\nX22\nthree\nX333\n"

    found = [m.group(1) for m in _FIXED.finditer(text)]
    print("fixed_finditer " + ",".join(found))

    m = _FIXED.search(text)
    print("fixed_search_first " + str(m.group(1) if m else None))

    # A match that starts the subject still works: offset 0 is also a line
    # boundary, so the lookbehind (nothing precedes it) is satisfied.
    m2 = _FIXED.search("X9\nrest\n")
    print("fixed_at_start " + str(m2.group(1) if m2 else None))

    # No match at all when X is not at a line boundary (mid-line).
    m3 = _FIXED.search("noX5here\n")
    print("fixed_midline_none " + str(m3 is None))

    # The broken (`re.M`-flagged) pattern is documented, not exercised for
    # a specific value here: whether it matches only at offset 0 or not at
    # all is exactly the platform-dependent behavior this file exists to
    # keep out of the fixed helpers above. Compiling it is the only claim.
    print("broken_compiles " + str(_BROKEN_M is not None))
    return None


if __name__ == "__main__":
    main()

# Guarded rather than a bare `main()`: this module has module-level globals
# (`_BROKEN_M`, `_FIXED`), so py2c emits an initializer that executes the
# top-level statements -- and it *also* calls `main` as the entry point. An
# unguarded call therefore ran twice natively and once under CPython, and
# the diff blamed the regex fix instead of the double call.
