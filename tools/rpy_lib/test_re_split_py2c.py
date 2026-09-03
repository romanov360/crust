"""`re.split(pattern, text)`: the module-level function, not `str.split`.

`"split"` is both a string method and a name in the `re` module, and the
call dispatcher checked the method name before it checked whether the
receiver was actually the `re` module. `re.finditer`/`re.findall`/`re.sub`
all dodge this -- none of those names collide with a string method -- so
`re.split` was the one spelling that fell into `str.split`'s lowering:
the *pattern* (`node.args[0]`) became the separator and the *text*
(`node.args[1]`) was dropped on the floor, receiver-as-string included.
`tools/cpprust.py` calls it this way ten times, all to split a qualified
name on `.`/`->` -- see `_named_object` and the field-qualification pass
in `_emit_class`.

Also covers the case that motivated fixing this rather than just avoiding
it: `re.split` with a pattern that can match the empty string. CPython's
rule reads like it should suppress an empty match adjacent to the last
split, but it does not -- every match `finditer` would report becomes its
own split point, verified directly against CPython below rather than
assumed from the docs.
"""
import re


def main():
    chain = [p for p in re.split(r"\s*(?:\.|->)\s*", "a.b->c") if p]
    print("chain " + ",".join(chain))

    single = [p for p in re.split(r"\s*(?:\.|->)\s*", "x") if p]
    print("single " + ",".join(single))

    # A zero-width split point (used in cpprust.py to break a translation
    # unit into per-`assert` chunks before parsing).
    parts = re.split(r"(?=\bassert\b)", "assert x > 0; assert y > 0; z")
    print("lookahead " + "|".join(parts))

    # Empty-match edges: every match finditer reports is its own split,
    # with no suppression for one landing where the previous split ended.
    print("starred " + "|".join(re.split(r"x*", "abxxcxd")))
    print("leading " + "|".join(re.split(r"a*", "abc")))


main()
