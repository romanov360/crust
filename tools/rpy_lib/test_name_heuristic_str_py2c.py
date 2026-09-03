"""An untyped parameter used only as a regex-match subject must not be
mistyped `int` just because its *name* matches py2c's int-by-convention
fallback list.

`infer_from_name` is the last resort for a parameter with no annotation:
guess a C scalar type from common naming conventions ("i", "count", "len",
"line", ...) so a numeric loop index does not have to be boxed as `obj`
just to compile. It is a *name*-only heuristic, and "line" is in its int
list (a line *number*) -- the wrong guess for a parameter that is actually
one line of source *text*.

`tools/cpprust.py`'s `_cond_value(line, defines)` was exactly this: `line`
is a string, matched against several compiled patterns via `.match()`, but
its inferred C parameter type came out `int`. Every caller's string
argument was then silently coerced to that `int` slot at the call
boundary -- `AS_INT()` on an `obj` that was actually a T_STR, or a raw
`char*` truncated straight into a 32-bit int with no cast -- and the
function's own body then handed that garbage back out as the subject of
`.match()`, segfaulting inside the regex engine. The failure was latent
for a long time: it only fires once a caller actually reaches this
function with a real value, and `_cond_value`'s own caller
(`_eval_conditionals`) was, until a separate fix, never invoked on a
spliced header's content at all.

The general fix is `_param_used_as_regex_subject` in py2c.py: an untyped
parameter that is the text argument of a `.match`/`.search`/`.finditer`/
`.findall`/`.sub` call, or of module-level `re.match`/`re.search`, is
never left to the name heuristic -- the same class of override
`_param_used_in_str_compare` already is for `==`/`!=` against a string
literal. This test uses "line" as the parameter name (matching
`_cond_value`'s own shape) so a regression in that specific override is
caught, not just the general mechanism.
"""
import re

_HASH_LINE = re.compile(r"^\s*#")


def line_is_directive(line):
    # `line` is int-by-name (a line *number*, by convention), but genuinely
    # holds a line of source *text* here -- `_cond_value`'s exact shape.
    return _HASH_LINE.match(line) is not None


def count_directive_lines(text):
    n = 0
    for line in text.split("\n"):
        if line_is_directive(line):
            n += 1
    return n


def main():
    text = "a\n#include <x>\nb\n#define Y\nc\n"
    print("count " + str(count_directive_lines(text)))
    print("direct " + str(line_is_directive("  #if FOO")))
    print("not_hash " + str(line_is_directive("plain text")))
    return None


if __name__ == "__main__":
    main()

# Guarded rather than a bare `main()`: this module has a module-level global
# (`_HASH_LINE`), so py2c emits an initializer that executes the top-level
# statements -- and it *also* calls `main` as the entry point. An unguarded
# call therefore ran twice natively and once under CPython, and the diff
# blamed the fix instead of the double call.
