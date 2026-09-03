"""`.index()` on a local whose *static* type py2c could not narrow to
`char*` -- because it was assigned from a slice, and `value_ctype` reports
generic `obj` for every `x[a:b]`, string or list alike -- must still work
when the value is actually a string at runtime, not abort the whole
process.

The call-site dispatch (`func.attr == "index" and ... value_ctype(...) !=
"char*"`) routes anything it cannot prove is a string to `list_index`,
which used to unconditionally `abort()` once it found the receiver's tag
was not `T_LIST` -- reasonable for an actual list holding no match
(CPython raises there too), wrong for a string that only *looks* untyped
to the static pass. `tools/cpprust.py`'s `_monomorphise_function_templates`
hits this exactly: `probe_body0 = text[t["start"]:t["end"]]` is a slice of
a known `char*`, so it is always a string at runtime, but its local is
declared `obj` in the generated C -- and `probe_body0.index("<")` a few
lines later crashed the native binary the first time a real template
definition (reached only via a real litehtml source file) made this
function actually run, immediately after `list_index` was reached with a
T_STR receiver.

The fix is in `list_index` itself: a `T_STR` receiver (paired with a
`T_STR` needle) delegates to `str_find`, the same search `str.index`
already uses, rather than falling straight to the abort. A genuine list
miss is unaffected and still aborts -- see `test_str_index_py2c.py`,
which pins `xs.index("operator")` succeeding on a real list.
"""


def first_angle_index(whole):
    # `whole` is reassigned from a *slice* of itself before this call, the
    # same shape as `probe_body0` in `_monomorphise_function_templates`:
    # always a string at runtime, but not provably `char*` to the static
    # pass once it has gone through a slice.
    whole = whole[0:len(whole)]
    return whole.index("<")


def main():
    print("angle " + str(first_angle_index("sum<A, B, C>(1, 2)")))
    return None


main()
