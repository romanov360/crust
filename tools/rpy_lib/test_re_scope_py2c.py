"""Two functions, each with its own local `pat = re.compile(...)`, must not
be confused with each other -- and a closure that captures a `pat`-named
local from its enclosing function must still resolve to *that* pattern.

py2c's regex pre-pass originally tracked "names bound to a compiled
pattern" as a flat set of bare strings across the whole file: every
`NAME = re.compile(...)` assignment, anywhere, added `NAME` to the set with
no notion of which function it was in. `tools/cpprust.py` has several
unrelated functions that each name a local `pat` for their own
`re.compile(...)` (`_check_ref_returns`, and others), plus `pat` as the
parameter of `_anchored_finditer` -- the one real generator in that file.
Whole-file, name-only tracking meant every one of those was silently
merged into a single "pat is always a compiled pattern" fact, so a call
like `pat.finditer(...)` in a function whose `pat` meant something else
entirely (or was never assigned there at all) lowered to a regex-matcher
call anyway, using *whichever* pattern happened to be tracked -- the wrong
one, or a dangling matcher id from an unrelated function.

The fix scopes each tracked name to the `id()` of the `FunctionDef` (or
`None` for module level) it was assigned in, via `_walk_with_scope`, and
`_regex_name_in_scope` checks the *current* function's id against that set
before treating a bare name as a known pattern. The one legitimate
cross-scope case -- a nested function closing over an enclosing local that
really is the same pattern, lifted to file scope by
`convert_block_closures` with its own, different `FunctionDef` id -- is
carried forward explicitly: each captured name's valid-scope set gains the
lifted function's id too, so a closure reading its own capture is not
mistaken for an unrelated same-named local the way the two module-level
functions below would be without the fix.
"""
import re


def scan_digits(text):
    pat = re.compile(r"\d+")
    return [m.group(0) for m in pat.finditer(text)]


def scan_words(text):
    pat = re.compile(r"[a-z]+")
    return [m.group(0) for m in pat.finditer(text)]


def make_scanner():
    # A nested closure capturing an enclosing local that really is its own
    # `re.compile(...)` -- the shape `tools/cpprust.py` actually has
    # (`call_re`/`agg_re`, captured by a lifted closure). `convert_block_closures`
    # lifts `scan` to file scope with `pat` as its own, same-named parameter,
    # a *different* `FunctionDef` id from `make_scanner`'s -- the case the
    # scope-propagation loop exists to keep working.
    pat = re.compile(r"[A-Z]+")

    def scan(text):
        return [m.group(0) for m in pat.finditer(text)]
    return scan


def main():
    text = "a1 b22 c333"
    print("digits " + ",".join(scan_digits(text)))
    print("words " + ",".join(scan_words(text)))

    scanner = make_scanner()
    print("caps " + ",".join(scanner("Hello WORLD foo BAR")))
    return None


main()
