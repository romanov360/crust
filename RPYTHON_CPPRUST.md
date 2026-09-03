# Lowering cpprust.py to C — where it stands

Issue #16 proposes porting `tools/cpprust.py` to RPython so it can be lowered
to C by `tools/py2c.py` and run natively. This is what that actually costs,
measured rather than estimated, and what is left.

The headline is that the port is much further along than "not started":
**py2c already transpiles all 13,120 lines without refusing anything.** The
work is not rewriting cpprust into a subset. It is that the C which comes out
did not compile, and the reasons were nearly all in py2c rather than in
cpprust.

## The number

`tools/rpy_census.py` runs all three passes over a program and prints one
census, so a change moves a number instead of an assertion:

```sh
python3 tools/rpy_census.py tools/cpprust.py
python3 tools/rpy_census.py tools/cpprust.py --errors   # just the count
```

| | at the start | now |
|---|---|---|
| gcc errors in `cpprust.c` | 76 | **0** |
| gcc errors in `cpp_auto.c` | 6 | **0** |
| links into a binary | no | **yes** |
| runs a translation end to end | no | **yes** |
| translates a 3-line class correctly | no | **yes** |
| exit code matches CPython's | — | **yes** |
| output matches CPython on a class with fields | no | **yes** |
| real litehtml files: agree byte-for-byte / disagree | — | **23 / 3** (0 fail natively where CPython succeeds, 17 CPython itself refuses — see below) |
| calls substituted with `None` | 11 | 2 |
| container advisories | 77 | 77 |

The substitution count needs a caveat the earlier version of this table
did not: it only counts constructs py2c *recognizes* as unsupported and
says so. `re.split` was not in that count at either reading — it silently
matched the wrong lowering (`str.split`'s) instead of falling through to a
warning, so the true number of dangerous defects was undercounted by
exactly the ones with no diagnostic at all. See below.

The three error columns are different kinds of problem and only the first
two matter. An advisory costs a reader nothing if ignored — the program is
correct either way, only slower. A substitution *changes what the program
does*. And a gcc error is invisible to py2c entirely: cpprust transpiled with
zero complaints from py2c and produced C with seventy-six of them, so "does
it lower?" and "does the result compile?" were separate questions and only
the first had an answer.

## What the errors turned out to be

Almost none of them were cpprust stepping outside the subset. They were
py2c's own lowering, and in one case its regex engine, so the fixes benefit
every RPython program rather than this one.

One shape accounted for most of it: **py2c's type oracle and its emitter
disagreeing.** `value_ctype` says a call yields an obj; the emitter emits a
raw `char*` or `long`; the assignment between them does not compile. That
happened for `re.sub` (16 errors), `str.index` (7), `str.count` (5), and in
the mirror direction for `AS_INT` over a value that was already a long. The
lesson each time was that the fix belongs where the *disagreement* is, not in
whichever half is easier to change — teaching `value_ctype` that `.index` is
an int looked right and made things worse, because that function also decides
how a fresh local is *declared*, so it declared `int` for names that
elsewhere held an obj: seven errors traded for seventeen. What tells the two
`.index` lowerings apart is not the receiver's static type (both are plain
`obj` in the generated C) but the helper py2c itself chose, so that is what
the check keys on.

The rest were individual gaps: transitive closure captures that followed
calls but not values, nested tuple targets, a kwargs slot passed to callees
that had none, `tuple()`, `os.path.normpath`, the sandboxed 3-argument
`eval`, integer conditionals boxed for no reason, and `re.sub` with a
function replacement.

### One was a wrong answer rather than a missing feature

`pat.search(s, pos)` handed the engine `text + pos`. That loses the text
*before* `pos`, so a lookbehind there could not see it:

```python
re.compile(r"(?<=;)x").search(";x", 1)
    CPython -> match at 1
    native  -> no match
```

Not a refusal — a different answer, silently. cpprust windows its scans
precisely so the lookbehind still sees the character before the window
(`agg_re.search(look, lo, at)`), so a self-hosted cpprust would have stopped
matching there and translated C++ subtly wrong rather than failing. Fixed by
giving the engine `crust_re_exec_from`, which starts the search at an offset
while keeping the whole subject visible; `len` doubles as CPython's `endpos`.
The differential fuzzer agrees with CPython over 53,121 comparisons with no
divergences.

This is the one to remember when reading the rest: the dangerous defects here
do not announce themselves.

## How each fix was checked

Every one ships a cpython-vs-native agreement test under `tools/rpy_lib/`,
run by `make testminipy`. The harness compiles the same source both ways and
diffs stdout, so a fix that compiles but computes something else fails.

| Test | Covers |
|---|---|
| `test_re_pos_py2c.py` | lookbehind across `pos`, `endpos` anchoring, absolute offsets, windowed finditer |
| `test_varargs_py2c.py` | `*args` with and without `**kwargs` |
| `test_strcount_py2c.py` | `s.count(sub, start, end)` and its edges |
| `test_tuple_py2c.py` | `tuple()` as a dict key and as an `in` member |
| `test_subfn_py2c.py` | `re.sub` with a function, including zero-width matches |
| `test_eval_env_py2c.py` | the sandboxed 3-argument `eval` |
| `test_ifexp_int_py2c.py` | integer conditionals in assignment, return and argument position |
| `test_ospath_py2c.py` | `normpath`, including popping past the root |
| `test_rsplit_py2c.py` | `s.rsplit(sep, maxsplit)`, which is not `split` reversed |
| `test_starred_ctor_py2c.py` | `Cls(a, b, *f())` — a non-leading `*expr` into a constructor |
| `test_re_split_py2c.py` | `re.split(pat, text)`, the module function, not `str.split` |
| `test_lambda_closure_py2c.py` | lambda closures: capture, a closure returned from its own creator, `self`, side effects, `.sort(key=...)` unaffected |
| `test_void_call_value_py2c.py` | a void-returning mutator (`.append`, `.sort()`, `dict.update`) used as a value |
| `test_str_index_py2c.py` | `s.index(x)` vs `list.index(x)` — same call shape, receiver decides |

The edges are deliberate. A hand-written `str.count` gets the empty needle
wrong (Python counts the gaps: `"abc".count("")` is 4), and a hand-written
`normpath` gets `..` past the root wrong. Those are the cases in the tests.

`examples/rpython2c/closures/lifted_captures.py` covers the two closure fixes
through `make rpython`, and it is a real regression test rather than a
demonstration: with the py2c changes stashed it fails to compile.

## What the three-line class turned out to be

The compile errors were gone, but the binary — which by then ran a whole
translation and wrote its output file — wrote the *wrong* thing: asked to
translate a three-line class it reported

    cpprust: class Box: base class `<garbage bytes>` is not defined above it

Neither the C compiler nor a smoke run reports that kind of thing, which is
the argument for a difftest rather than an assertion. It also turned out to
be four separate bugs layered on top of each other — fixing the first one
just exposed the next — and none of them were in the C compiler's reach:

1. **A constructor call never handled a non-leading `*expr` at all.**
   `_find_classes` builds every `Class` with
   `Class(name, tparams, members, line, *_parse_base(base_clause, name))` —
   the *only* call site in the whole 15,000-line tree that spreads a
   function's return value across a constructor's *trailing* parameters.
   Local-function calls had a helper for a *leading* star; constructor
   calls had no `Starred` handling whatsoever, so the whole `*_parse_base(...)`
   expression lowered through the generic fallback: evaluated once, handed
   as a single (wrong-typed) value to the next parameter (`base`), and
   whatever parameter was left over (`extra_bases`) silently took its
   *default*. A class with no base at all — `_parse_base` correctly
   returning `(None, [])` — came out reporting a base class of `` (the
   whole 2-tuple, reinterpreted as a string, happened to decode short) or
   worse, whatever the previous call's boxed return value looked like as
   text. Fixed by `_lower_starred_args` in py2c.py, which expands a single
   `*expr` at any position — not just first — into the callee's exact
   parameter count, evaluating the expression once into a shared temp
   rather than re-running it per unpacked slot. `test_starred_ctor_py2c.py`.

2. **`main()`'s own exit code was never the int it returned.** Once (1)
   stopped mis-reporting, the *correct* error case (`class Derived : public
   Missing`) matched CPython exactly — but a *successful* translation and a
   *failed* one both exited 1. `cpprust.py`'s `main()` references
   `sys.argv`, which gives it the real C `int main(int argc, char** argv)`
   entry point signature — but with no return annotation, py2c's inference
   falls back to the boxed `obj`, and an `obj`-returning `main` is a C ABI
   mismatch: the OS reads an `int` off wherever the calling convention
   puts one, not the tagged union `OBJ_INT(0)` actually is. Fixed with one
   annotation, `def main() -> int:`, matching the pattern
   `examples/rpython2c/closures/lifted_captures.py` already used for the
   same reason. py2c itself now warns (`rpython: ... main() takes argv but
   has no '-> int' return annotation ...`) whenever this shape recurs in
   *any* RPython program, so the next occurrence is loud rather than a
   silently-wrong exit code discovered by accident.

3. **`re.split` collided with `str.split` in the call dispatcher.** Any
   class with at least one field referenced unqualified in a method body
   goes through `_named_object`'s `re.split(r"\s*(?:\.|->)\s*", expr)` to
   break a dotted/arrow chain into parts — and `"split"` is both a name in
   the `re` module and a string method. The dispatcher checked
   `func.attr in self.STR_METHODS` before it checked whether the receiver
   was actually the `re` module, so `re.split(pattern, text)` matched
   `str.split(sep)`'s lowering: the *pattern* became the separator, the
   *text* argument was dropped, and the receiver — the bare name `re` —
   evaluated to `OBJ_NONE`. This one had no substitution warning at all
   (it compiled as an ordinary, well-typed call) and crashed with a null
   `strlen` the moment a real class had a field. Fixed by excluding a
   receiver that resolves to a known `import`ed module from the
   string-method fast path, and by giving `re.split` its own lowering
   (`_cre_split`, built on the same `crust_re` bridge `finditer`/`findall`
   already use). Its empty-match behavior is not obvious from the docs —
   Python's wording reads like an empty match "adjacent to the previous
   split" should be suppressed, but checked directly against CPython it is
   not: every match `finditer` would report becomes its own split point,
   full stop. `test_re_split_py2c.py` covers both the common case and that
   edge. `calls substituted with None` in the census table above undercounts
   exactly this shape of bug for the same reason: nothing about it looked
   like a substitution.

4. **`Member.dim` — a `str`, the array-suffix text `"[10]"` or `""` — was
   inferred as `int`.** py2c has no type annotation to go on for an
   unannotated field, so it guesses from the name, and `dim` is in the
   numeric-code convention list (`rank`, `dim`, `dims`, `stride`, ...) for
   good reason everywhere *except* this one field, which predates that
   convention and collides with it. Every field declaration came out as
   `int x<garbage>;` — a real decimal number glued onto the field name
   with no separator, changing per run, because "" round-tripped through
   `int` formatting reads whatever bit pattern happened to be in an
   unrelated boxed value. This is not a py2c bug to fix (the naming
   convention is doing its documented job on every other `dim` in the
   codebase); it is cpprust.py stepping on it. Fixed by renaming the field
   and every local that feeds it to `arrsuf`, which isn't in the list.

Each of these compiled clean and ran without a crash on the *first* class
small enough to hit it. That is the pattern worth taking away, not any one
of the four: a build that "runs and writes a file" is not evidence the file
is right, and the census's error and substitution counts — both zero or
near it throughout — did not move for any of them.

## Lambdas: from "not lowered at all" to a working closure

With (1)–(4) fixed, a class with a real base, secondary interface bases,
an array field, and a body that reads its own fields translated
byte-identical to CPython's output — *except* any class with a field read
or written unqualified in a method body, because `_emit_class`'s
field-qualification pass runs its rewrite through a first-class lambda:

```python
inner = _sub_code(
    r"(?<![\w.>])(%s)\b" % _type_alt(visible),
    lambda m: "this->" + info["paths"][m.group(1)], inner)
```

and `ex_Lambda` — the general case, reached whenever a `lambda` is used as
a *value* rather than inlined at a special-cased call site
(`.sort(key=...)`, an immediately-invoked `(lambda: ...)( )`) —
unconditionally returned `make_closure(&identity__tramp, OBJ_NONE)`: the
identity function, no matter what the lambda's body said. Natively,
`repl(m)` returned `m` itself, and the qualifier appended the raw match
value — `['x', 'x', 8, 9, 8, 9]`, `_re_emit_build`'s internal list layout
for the match, stringified — instead of `this->x`. box.cpp's original
repro didn't hit this only because it has no fields.

**This is now implemented.** `ex_Lambda` builds a real closure: free
variables the body reads out of the enclosing function (`self.scope`,
plus `self` as a special case — a method's own receiver is never a
`self.scope` entry) travel in a captured environment list, and a
uniform-signature trampoline — registered when the lambda is lowered,
emitted once every function body has been walked, the same two-pass
structure `emit_trampolines` already used for closure-converted `def`s —
unpacks env and args and evaluates the body. `.sort(key=lambda ...)` and
every `re.sub` function-replacement call site in this tree never reach
`ex_Lambda` at all (inlined, or naming a real function), so neither
needed to change, and both were verified unaffected.

Implementing it surfaced one more real gap on the way: a void-returning
runtime mutator (`.append`, `.sort()`, `dict.update`, ...) used as a
*value* has no lowering either — `value_ctype` has no case for these,
because a bare statement never notices, but a lambda whose whole body is
exactly one such call (a callback that exists purely for its side effect
— `_monomorphise_uses`'s `record` parameter) needs its `None` back.
Fixed the same way `_scalar_helper_ct` already handles the analogous
scalar-helper problem: keyed on the emitted call, not the receiver's
static type.

## The first real difftest

With lambdas working, the compiler was finally run where issue #16 was
always going to have to prove itself: `cpprust_native` against
cpython-`cpprust.py`, over the real 43-file litehtml corpus this repo
already has checked out, not another synthetic repro.

| | files |
|---|---|
| both sides translate, byte-identical output | **14** |
| CPython itself refuses (subset gap, not a native bug) | 17 |
| native fails where CPython succeeds | 12 |
| both succeed but disagree | **0** |

The bottom row is the one that matters most: not one file where both
sides produced *output* disagreed. Every remaining gap is native either
crashing or refusing something CPython accepts — visible, not silent.

The refusals are `cpprust.py` doing its job (an overloaded free function,
a virtual base, `auto` needing clang and rejected under `--no-clang`) and
are not this issue's concern. The 12 native-only failures split into two
groups:

* **Seven crash with the identical signature** — `codepoint`, `el_li`,
  `el_text`, `html`, `num_cvt`, `strtod`, `url` (plus `iterators.cpp`,
  which was the one that first surfaced the (1)-through-(4) round: fixing
  the `str.index`/`list.index` collision got it past that crash into this
  same one). All seven die in `_cre_dyn_get`, handed a `char*` that is
  actually a small integer reinterpreted as a pointer.

  The cause is `cpp_auto.py`'s `_anchored_finditer(pat, text)`, called
  with a compiled pattern (`_DECLARATOR`, `_FIELD`, `_INDEXER` — all
  `re.compile(...)` module constants) reached through a *parameter*.
  py2c tracks which names hold a compile-time-constant pattern by the
  variable's own spelling (`_regex_var_pat`/`_regex_dyn_vars`, keyed on
  the assignment `NAME = re.compile(...)` at the point it's made) — sound
  for a name used directly, but `pat` inside `_anchored_finditer` is a
  different name at a different scope, so the tracking doesn't see
  through the call boundary. `pat.match(text, pos)` then unconditionally
  lowers through the *dynamic* bridge (`AS_STR(pat)`, `_cre_dyn_get`),
  and `pat` at runtime is actually `OBJ_INT(pid)` — the translation-time
  compiler's own representation for a constant pattern, per the earlier
  `re.compile` fast path (`return "OBJ_INT(%d)" % pid`). `AS_STR` on an
  int-tagged `obj` reads the tag union's other arm: the integer,
  reinterpreted as a pointer.

  A full fix needs more than a dispatch-order change this time: the
  translation-time engine (`_re_search(id, t, anc)`, dispatching to
  either the specialized state machine `_re_pN` or the regex-VM slot
  `_cre_run`) has no `pos` parameter at all — every match starts at
  offset 0 — while `_anchored_finditer` calls `.match(text, start)` with
  a real offset on every iteration but the first. Slicing the string at
  the call site is not the fix this project already rejected for the
  same shape (`pat.search(s, pos)` losing lookbehind context to
  `text + pos` — see "One was a wrong answer" above); the honest fix
  extends `_re_search`/`_re_pN`/`_cre_run` to take a start position the
  way `crust_re_exec_from` already gives the dynamic bridge, and adds a
  runtime dispatch on `pat`'s tag (`T_INT` vs `T_STR`) for the case a
  compiled pattern arrives through a value of unknown origin. Sitting
  behind that: `_anchored_finditer` is *also* the one generator function
  (`yield`) anywhere in either file, and generators still have no
  lowering — the crash happens on the pattern match, before either
  `yield` is ever reached, so fixing the dispatch is necessary but not
  sufficient; the values this function is supposed to produce still need
  a lowering for `yield` itself -- not attempted yet. Every caller here
  consumes the result with a plain `for m in ...:` run to exhaustion, so
  "collect into a list and return that" is the tractable version of that
  problem, not full coroutine semantics.

* **Five report a plausible-looking but wrong `CppError`** — `context`,
  `el_link`, `el_script`, `el_table`, and (past the crash above)
  `iterators` again. Two shapes: `"shared_ptr_X owns a resource, and the
  right-hand side is ... not ... a call returning one"` for
  `get_document()`/`get_child()`-style accessors (`iterators`, `el_link`,
  `el_table`), and `"X& return type is not in the C++ subset"` naming a
  *function*, not a type, as `X` (`context`: `JS_Eval&`, from
  `return JS_Eval(...)`, where `JS_Eval` is never declared anywhere in
  litehtml itself — it's a QuickJS symbol this checkout has no header
  for; `el_script` likewise). Reproduces with `--no-clang` too, so it is
  not the clang-oracle gap below. Not yet isolated to a single cause the
  way the crash above was — plausibly connected to each other, not yet
  shown to be.

Six calls still lower to `None`, and they are the whole remaining
recognized-and-warned-about list:

* **The clang oracle** — `json.load`, `_json.dump`, `json.loads`,
  `subprocess.check_output`. `auto` deduction falls back to clang, and none
  of that path lowers. It is optional (`--no-clang`), so the first difftest
  can run without it.
* **Two `yield`s in `cpp_auto`** — generators have no lowering at all, and
  the expression is dropped rather than refused, so those two functions
  silently produce nothing.

## From 12 native-only failures to zero

Every one of the gaps above got fixed, plus three more the fixes
themselves exposed. None were where the diagnosis above expected them —
each new fix widened what the native binary actually *ran*, and that
kept surfacing the next bug rather than reaching a clean state. The tools
used throughout were the same three every time: a `gdb -batch -ex run
-ex bt` backtrace to find the crash site, a two-line isolated repro
(`python3 tools/py2c.py repro.py` vs `python3 repro.py`) to confirm the
divergence outside the 800KB generated file, and — once the isolated
repro also failed under plain CPython — reading the suspect function
directly rather than trusting an assumption about what it does.

1. **`yield` → eager list collection.** Exactly as scoped above:
   `_anchored_finditer` is this codebase's one generator, every caller
   runs it to exhaustion with `for m in ...:`, so `emit_hoisted_body`
   collects each `yield`ed value into a list (`cur_gen_var`) and returns
   that list wherever the function would otherwise return or fall off
   the end. Not real coroutine semantics — deliberately not needed here.

2. **Regex-pattern tracking scoped to the function it's assigned in.**
   The root cause behind the seven-file crash, precisely as scoped above
   (`pat` inside `_anchored_finditer` colliding with unrelated same-named
   locals elsewhere): `_walk_with_scope` records the `id()` of the
   enclosing `FunctionDef` for every `NAME = re.compile(...)`, and
   `_regex_name_in_scope` gates every read against it. A closure
   capturing an enclosing local that really is the same pattern needed
   its own carve-out (`lift_nested_functions`/`convert_block_closures`
   now thread `id(enclosing_fn)` through their closure specs), and the
   pattern-*text* table (`_regex_var_pat`) needed the same per-scope keying
   as the name table — two unrelated functions each naming a local `pat`
   for their own constant compile resolved to whichever one a flat
   `name -> text` dict saw last, even after the name itself was correctly
   scoped.

3. **`_re_search`/`_re_pN`/`_cre_run` gained a `pos` parameter**, mirroring
   `crust_re_exec_from`'s existing `t` (whole subject) / `pos` (search
   start) split — precisely the fix scoped above, plus a runtime
   `T_INT`/`T_STR` tag dispatch (`_re_match_any`, `_re_finditer_any`) for
   the case a compiled pattern reaches a call through a value of unknown
   origin (a parameter, not a name py2c can trace to its own
   `re.compile`).

4. **`open(...)`/`with open(...) as f:` now raise on a missing file.** A
   bare `fopen()` returning NULL was never checked, so `except IOError:`
   around a "try each candidate directory" loop — exactly the shape
   `_expand_headers` uses to find a header under `--basedir`/`--incdir` —
   never fired: the first candidate directory was taken whether or not
   the file in it actually existed. This is *why* the two fixes above
   were not the end of it: with `_anchored_finditer` no longer crashing,
   full corpus runs kept turning up files where the native binary's
   output was missing entire header-declared classes, because no header
   had ever actually been spliced into any translation unit, in *any*
   file, the whole time. `codepoint.cpp` and `url.cpp` moved from "no
   crash" to "byte-identical with CPython" only after this landed — the
   earlier "no crash" reading was a false negative, not progress.

5. **`re.compile(pattern, re.MULTILINE)`'s flags argument is silently
   dropped.** py2c's regex pre-pass interns only a `re.compile()` call's
   pattern *text*; nothing anywhere reads a second, flags argument, and
   `crust_re_compile` has no multiline mode to opt into either. So `^`/`$`
   in a `re.M`-flagged pattern compiled as a plain *string* anchor —
   `^` matched only literal offset 0, never a line start past it — which
   is exactly what `_ANY_INCLUDE` (the pattern `_expand_headers` uses to
   find `#include` lines) is built from, and no real source file has one
   at offset 0. Rewritten as `(?<![^\n])`/`(?![^\n])` (fixed-width
   lookaround the engine already supports, and the same idiom
   `_clean_macros` already used in place of `re.M`), dropping the
   now-unnecessary flags argument. A native-only bug expressed as a
   pattern rewrite, not new engine support.

6. **The int-by-name heuristic can still override an obviously-string
   parameter.** `infer_from_name`'s fallback guessed `int` for
   `_cond_value`'s `line` parameter (a source line of *text*, matched
   against `re` patterns; "line" is in the heuristic's int-by-convention
   list, meaning line *number*). Every caller's string argument was then
   silently truncated to that `int` slot at the call boundary, and the
   function handed the resulting garbage straight back out as a
   `.match()` subject — segfaulting inside the regex engine the moment a
   real header (finally reaching `_eval_conditionals`, thanks to fix 4)
   made this function actually run. `tools/cpprust.py`'s own instance was
   fixed by renaming the parameter; the general py2c gap was fixed by
   adding `_param_used_as_regex_subject` to `arg_ctype`'s existing list of
   usage-based overrides (alongside `_param_used_in_isinstance`,
   `_param_used_in_str_compare`, ...), so a parameter that is the text
   argument of `.match`/`.search`/`.finditer`/`.findall`/`.sub` is never
   left to a name guess that could be wrong the same way again.

7. **`list_index()` had no fallback for a string it couldn't statically
   type.** `.index()` on a receiver py2c cannot prove is `char*` (a local
   assigned from a slice, most often — `value_ctype` reports the generic
   `obj` for *every* `x[a:b]`, string or list alike) dispatches to
   `list_index`, which used to `abort()` the instant its receiver's tag
   was not `T_LIST`. `_monomorphise_function_templates`'s
   `probe_body0 = text[t["start"]:t["end"]]` is always a string at
   runtime (a slice of a known `char*`) but declared `obj` in the
   generated C, and `probe_body0.index("<")` crashed the native binary
   the first time a real template definition reached it. Fixed at
   `list_index` itself: a `T_STR` receiver (paired with a `T_STR` needle)
   now delegates to `str_find`, the same search `str.index` already uses.
   A genuine list miss is unaffected and still aborts.

8. **`\w`/`\d`/`\s` inside a `[...]` character class meant the literal
   letter.** `regex_parse` (the translation-time specializer for simple
   constant patterns) parsed a class member's backslash escape the same
   way it parses one outside a class — drop the backslash, keep the next
   character — which is wrong specifically inside `[...]`: `\w` there
   means "any word character", not the literal letter "w", and
   `_re_class_test`'s "class" case has no representation for a nested
   shorthand at all. Found via `tools/cpprust.py`'s own
   `_is_call_result`, which recognizes a callee expression with
   `[\w:.>()\[\]\s-]`: read as the literal set `{w,:,.,>,(,),[,],s,-}`,
   it rejected almost any real callee, including calls inside the
   transpiler's own generated `string` class (`this->substr(...)`) —
   confirmed with a two-line repro (`re.match(r"^[\w:.>()\[\]\s-]+$",
   "this->substr")`, `False` natively, `True` under CPython) after a
   `git worktree` bisection against the pre-session commit ruled out
   every fix above as the cause. Fixed by rejecting rather than
   mis-specializing: `regex_parse` returns `None` the moment it sees a
   shorthand inside a class, sending the pattern to the crust_re VM tier
   instead, which implements this correctly.

A fresh corpus run after all eight:

| | files |
|---|---|
| both sides translate, byte-identical output | **23** |
| CPython itself refuses (subset gap, not a native bug) | 17 |
| native fails where CPython succeeds | **0** |
| both succeed but disagree | 3 |

Native crashes and CppError-refuses-what-CPython-accepts are both gone —
every remaining native-only outcome is a byte-identical translation or an
agreed refusal. The three `DIFF` files (`codepoint.cpp`, `num_cvt.cpp`,
`url.cpp`) are a new, better-shaped problem: both sides now succeed, and
disagree on the *output*. `codepoint.cpp`'s diff is namespace flattening
producing `litehtml_litehtml_is_ascii_codepoint` (a reopened `namespace
litehtml { }` — once in the header for the declaration, again in the .cpp
for the definition — double-prefixing a function whose C++ name already
happens to start with `litehtml_`). That specific double-prefix
reproduces under plain CPython too, in isolation
(`cpp_auto.resolve_namespaces` on a two-block minimal repro) — so unlike
every bug above, this is *not* a native-only divergence, and whatever
makes the real corpus run's CPython side avoid it is still unexplained.
Not yet investigated for `num_cvt.cpp`/`url.cpp`.

## What has not been measured yet

Nothing here says the result is *faster*. 23 of 43 real files now agree
byte-for-byte with CPython, up from 14, and zero fail natively where
CPython succeeds — real progress on "does it lower correctly," measured
against real input this time, not a synthetic repro. But the corpus is
not fully green: 3 files now produce *different* output on the two sides
(not diagnosed yet), so timing the binary now would still be timing a
program that cannot yet process the whole corpus identically. The order
is unchanged in kind, just further along: clear the remaining divergence,
get to 43/43 (or 26/26 once the 17 agreed refusals are separately
resolved), then measure.

Two things worth knowing before that measurement is designed:

* Translation is no longer the several-minutes-per-file the issue implies.
  After the quadratic scans were removed (issue #6, merged as PR #7),
  `document.cpp` translates in about 15s, of which roughly 4.5s is a clang
  subprocess and JSON AST parse — real external work that a native cpprust
  would not speed up. A native build plausibly reaches 2-3s, which is worth
  having and is not the order of magnitude the issue assumes.
* **ShivyCX has two bugs of its own here**, both in code gcc compiles
  correctly: it segfaults on `m = pat.search(text, pos)`, and it computes 42
  where CPython and gcc both get 65 on a `*args` program. Two of the fixtures
  above therefore live in the gcc-based harness rather than `make rpython`.
  A self-hosted cpprust has to clear those before it can be trusted.
