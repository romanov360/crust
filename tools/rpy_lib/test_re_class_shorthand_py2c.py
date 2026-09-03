"""`\\w`/`\\d`/`\\s` (and their negations) *inside* a character class --
`[\\w:.-]`, not a bare `\\w` -- must mean what they mean everywhere else in
a pattern: any word/digit/space character, not the literal letter left
over once the backslash is stripped.

`regex_parse` (py2c's translation-time specializer for simple constant
patterns -- the tier that compiles a pattern straight to C comparisons,
with no engine or bytecode, when the pattern fits a narrow subset) parsed
a class member's escape the same way it parses an escape *outside* a
class (`\\.` -> literal `.`, `\\\\` -> literal `\\`): drop the backslash,
keep the next character. Inside `[...]` that is wrong for the six
shorthand escapes specifically -- `\\w` in a class is not the character
"w" -- and `_re_class_test`'s "class" case has no representation for a
nested shorthand at all (every item it emits is either a literal-char
comparison or an a-b range), so the mistake was silent: the specializer
still accepted the pattern and produced a matcher that tested for the
literal letter, with no error anywhere.

`tools/cpprust.py`'s own `_is_call_result` uses exactly this shape --
`[\\w:.>()\\[\\]\\s-]` -- to recognize a callee expression. With `\\w` and
`\\s` silently read as literal 'w' and 's', the check rejected almost any
real callee (`this->substr`, `foo.bar`, anything without a stray 'w' or
's' happening to appear in exactly the right spot) -- including calls
inside the transpiler's own generated `string` class, which the native
binary then refused to compile at all.

The fix rejects (returns None from `regex_parse`) rather than
mis-specializes: a shorthand inside a class sends the pattern to the
crust_re VM tier instead, which implements `\\w`/`\\d`/`\\s` correctly
inside a class the same as outside one.
"""
import re

WORDISH = re.compile(r"^[\w:.>()\[\]\s-]+$")
NOT_DIGIT_OR_SPACE = re.compile(r"^[^\d\s]+$")


def main():
    print("plain_word " + str(WORDISH.match("this->substr") is not None))
    print("with_paren " + str(WORDISH.match("foo(a, b)") is not None))
    print("bad_char " + str(WORDISH.match("a+b") is not None))

    print("letters_only " + str(NOT_DIGIT_OR_SPACE.match("abcXYZ") is not None))
    print("has_digit " + str(NOT_DIGIT_OR_SPACE.match("ab3c") is not None))
    print("has_space " + str(NOT_DIGIT_OR_SPACE.match("ab c") is not None))
    return None


if __name__ == "__main__":
    main()

# Guarded rather than a bare `main()`: this module has module-level globals
# (`WORDISH`, `NOT_DIGIT_OR_SPACE`), so py2c emits an initializer that
# executes the top-level statements -- and it *also* calls `main` as the
# entry point. An unguarded call therefore ran twice natively and once
# under CPython, and the diff blamed the fix instead of the double call.
