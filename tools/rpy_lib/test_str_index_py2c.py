"""`s.index(x)` with exactly one argument -- the shape that collides with
`list.index(x)`: same attribute name, same argument count, and only the
receiver's type says which the author meant.

The call dispatcher checked for this shape (`func.attr == "index" and
len(node.args) == 1`) before it checked whether the receiver was even a
string, so `s.index(x)` on a receiver py2c already knows is `char*` still
matched the list rule and lowered to `list_index` -- a *different runtime
contract*, not just the wrong function: CPython's `.index` raises when the
value is missing, and `list_index` matches that by aborting the whole
process, while `str.index` already relaxes it to "yields -1" (a missing
match is not the same as an error here; see the `find`/`index` comment in
`lower_str_method`) because callers rely on being able to probe. Handing a
boxed string to `list_index` compiled fine -- both are `obj` in the
generated C -- and then aborted on the first substring the string did not
happen to contain as an *element*.

`tools/cpprust.py` writes `sig[:sig.index("operator")]` this way (an
operator-overload signature, cut at the word "operator") -- reached only
by a real litehtml source file, `iterators.cpp`, which is what surfaced
this: `sig.index("operator")` on box.cpp-sized synthetic input never
happened to exercise it.

Fixing the dispatch order exposed a second, older gap right behind it:
`str_find` (the *no*-extra-argument form `s.index(x)`/`s.find(x)` share)
was missing from `_SCALAR_HELPERS` -- `str_find_from`/`str_find_range`
were listed, the plain `str_find` was not -- so `AS_INT(str_find(...))`
tried to read a `.u.i` field off a value that was already a raw `long`.
`as_long` (slice bounds, among other places) didn't consult
`_scalar_helper_ct` at all, unlike `coerce_to`/`wrap_obj`; the previous
dispatch bug made that unreachable too, for the same reason -- a 1-arg
`.index()` never got this far to find out.
"""


def main():
    sig = "int operator[](int i)"
    bits = sig[:sig.index("operator")].strip()
    print("slice " + bits)

    print("plain " + str("abc-def".index("-")))
    print("missing " + str("abc".find("z")))   # find: no exception either way

    xs = ["a", "b", "operator", "c"]
    print("list " + str(xs.index("operator")))


main()
