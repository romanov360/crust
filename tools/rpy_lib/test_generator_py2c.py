"""`yield` support, lowered as eager list collection.

Nothing in this codebase's own use of a generator ever partially consumes
it or resumes it after the caller does something else -- every call site is
`for x in gen(...):`, run to exhaustion. Under that restriction, collecting
every yielded value into a list up front and returning the list is
observationally identical to real generator/coroutine semantics, so that is
what py2c lowers `yield` to: a list, appended to at each `yield`, returned
wherever the function would otherwise fall off the end or hit a bare
`return`. This is not a general fix for arbitrary generator usage (a
generator that is never fully consumed, or is sent values via `.send()`,
would observe the difference) -- only for the run-to-exhaustion shape this
project actually uses.

Covers the two shapes yield actually takes here: a `while` loop that
`yield`s computed values and falls off the end (no explicit `return`), and
a `for` loop that conditionally `yield`s and also falls off the end. Both
exercise `emit_hoisted_body`'s fallback-return path, which has to return
the collected list instead of `OBJ_NONE` for a generator -- that fallback
originally fired *before* a redundant one added directly in `func_def`
ever ran, so the first version of this fix was dead code.
"""


def counter(n):
    i = 0
    while i < n:
        yield i * 2
        i += 1


def evens_only(xs):
    for x in xs:
        if x % 2 == 0:
            yield x


def main():
    total = 0
    items = []
    for v in counter(5):
        items.append(v)
        total += v
    print("items " + ",".join([str(x) for x in items]))
    print("total " + str(total))

    picked = []
    for v in evens_only([1, 2, 3, 4, 5, 6]):
        picked.append(v)
    print("picked " + ",".join([str(x) for x in picked]))
    return None


main()
