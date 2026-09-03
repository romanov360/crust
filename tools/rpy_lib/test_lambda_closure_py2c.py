"""A `lambda` used as a first-class value: assigned, handed to an ordinary
function, returned from one, or immediately invoked.

`.sort(key=lambda ...)` inlines the key lambda's body directly, and every
`re.sub` function-replacement call site in this tree names a real function
rather than writing one inline -- so neither of those ever reaches the
general lowering this test is actually about. Until it was implemented,
that general path unconditionally returned the identity closure: any
lambda doing more than `lambda x: x` silently became one that does
nothing but hand back its argument.

`tools/cpprust.py` depends on the general case directly: `_sub_code`
(field qualification, template substitution, every text-rewriting pass in
the file) calls its `repl` argument -- routinely a lambda closing over a
dict or a list built earlier in the same function -- through a first-class
closure. A class with a field used unqualified in a method body went
through exactly this, and reached the identity closure instead of the
real replacement; see RPYTHON_CPPRUST.md.
"""


def apply_twice(f, x):
    return f(f(x))


def make_adder(n):
    """A closure returned from the function that created it -- the
    captured environment has to outlive that function's own C stack
    frame, which a value captured *by value* into an env list does
    automatically."""
    return lambda x: x + n


class Counter(object):
    __slots__ = ("n",)

    def __init__(self, n):
        self.n = n

    def bump_maker(self):
        """`self` is captured too, and by reference in effect (the struct
        pointer itself, not a copy of its fields) -- a later mutation
        through `c.n = ...` is visible the next time the closure runs."""
        step = 2
        return lambda: self.n + step


def main():
    scale = 3
    offset = 5
    f = lambda v: v * scale + offset
    print("closure " + str(apply_twice(f, 1)))

    print("immediate " + str((lambda a, b: a * b + 1)(4, 5)))

    add7 = make_adder(7)
    print("returned " + str(add7(10)))

    # A closure whose body is called purely for its side effect -- a
    # callback pattern `_monomorphise_uses`'s `record` parameter uses.
    found = []
    record = lambda n, t: found.append((n, t))
    record("a", 1)
    record("b", 2)
    print("sideeffect " + str(len(found)) + " " +
          found[0][0] + str(found[1][1]))

    c = Counter(10)
    bump = c.bump_maker()
    print("selfcap " + str(bump()))
    c.n = 100
    print("selfcap2 " + str(bump()))

    # Unaffected by any of the above: still inlined, not a closure call.
    xs = [3, 1, 2]
    xs.sort(key=lambda v: -v)
    print("sortkey " + ",".join(str(v) for v in xs))


main()
