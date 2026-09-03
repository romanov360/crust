"""An in-place mutator (`.append`, `.sort`, `dict.update`, ...) used as a
*value* -- its Python return is always `None`, but the C runtime call
behind it (`list_append`, `list_sort`, `dict_update`, ...) returns nothing
at all: `void`. `value_ctype` has no case for these, because a bare
statement never notices -- `xs.append(x)` on its own line just compiles to
`list_append(xs, x);` and nothing reads a value that was never produced.

The gap only shows up once something *does* read it: a `return
lst.append(x)`, or -- the shape that surfaced this -- a lambda whose
entire body is the call, used as a callback purely for its side effect
(`tools/cpprust.py`'s `record` parameter to `_monomorphise_uses`). Before
this was fixed the generated C read `return list_append(...);` and gcc
refused it outright ("void value not ignored as it ought to be") --
caught at compile time here only because the lambda-closures fix (see
`test_lambda_closure_py2c.py`) made this shape reachable at all; as a
statement it would have compiled to something that runs, just never to
the `None` it should read back as.

The read of each mutated container is its own statement, after the call
that mutates it -- not folded into the same expression (`f() + ",".join
(xs)`). That would test something else entirely: C does not guarantee
which side of a `+` runs first, so a single expression reading `xs` on one
side while mutating it through a call on the other is not well-defined
regardless of how the call itself lowers, and is its own separate, real
gap -- see RPYTHON_CPPRUST.md -- not what this test is checking.
"""


def call_for_effect(f):
    return f()


def main():
    xs = [1, 2]
    r = call_for_effect(lambda: xs.append(3))
    print("append " + str(r) + " " + ",".join(str(v) for v in xs))

    d = {"a": 1}
    r = call_for_effect(lambda: d.update({"b": 2}))
    # Not `str(d.items())`: a tuple is a list in this runtime (see
    # test_tuple_py2c.py), so its repr brackets differ from CPython's by
    # design -- unrelated to what this test checks.
    pairs = ",".join(k + "=" + str(d[k]) for k in sorted(d.keys()))
    print("dictupdate " + str(r) + " " + pairs)

    ys = [3, 1, 2]
    r = call_for_effect(lambda: ys.sort())
    print("sort " + str(r) + " " + ",".join(str(v) for v in ys))

    zs = [1, 2, 3]
    r = call_for_effect(lambda: zs.remove(2))
    print("remove " + str(r) + " " + ",".join(str(v) for v in zs))


main()
