"""`Cls(a, b, *f())`: a constructor call with a non-leading, non-first
`*expr` spread over the trailing positional parameters.

`f()` here stands in for `cpprust.py`'s `_parse_base(...)`, called as
`Class(name, tparams, members, line, *_parse_base(base_clause, name))` --
the one call site in the whole file (and the only one anywhere in the
tools/ tree) that spreads a call's return value across a constructor's
tail parameters rather than leading them.

The dispatcher had two matching bugs. Constructor calls had no `Starred`
handling at all: the whole `*f()` expression lowered through the generic
fallback, which evaluates it once and hands the result -- a 2-tuple, not
two values -- to the *first* remaining parameter, then pads whatever is
left with that parameter's default. Local-function calls fared better but
only when the star came *first*; a leading-arg-then-star shape like this
one was never handled, so it does not help here either.

Silent, not refused: the class compiled and ran, and reported a base class
of `` (or worse, an unrelated boxed value re-interpreted as a string) for
a class the source never gave one to -- see RPYTHON_CPPRUST.md, "class
Box: base class `<garbage bytes>` is not defined above it".
"""


class Widget(object):
    __slots__ = ("name", "count", "kind", "extra")

    def __init__(self, name, count, kind=None, extra=None):
        self.name = name
        self.count = count
        self.kind = kind
        self.extra = extra or []


def split_kind(spec):
    """Stand-in for `_parse_base`: one 2-tuple return, spread at the call
    site -- `kind` may be None (no base), `extra` is always a list."""
    if not spec:
        return None, []
    parts = spec.split(",")
    return parts[0], parts[1:]


def describe(w):
    k = w.kind if w.kind is not None else "(none)"
    return (w.name + " x" + str(w.count) + " kind=" + k +
            " extra=" + ",".join(w.extra))


def main():
    a = Widget("gear", 3, *split_kind(""))
    b = Widget("bolt", 5, *split_kind("metal,shiny,small"))
    print(describe(a))
    print(describe(b))


main()
