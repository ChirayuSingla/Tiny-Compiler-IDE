# Conservative complexity analysis

`complexity.py` analyzes the semantically annotated AST and real symbol identities from a successful compilation. It never executes sample input to infer complexity. Runtime instruction counts are measured separately by the VM and do not feed the estimate.

## Cost model

The result is an asymptotic upper bound for a fixed source program, treating each scalar AST operation as O(1). A parameter such as n denotes the magnitude of the initial runtime integer input named n, clamped to at least 1. Logarithmic terms use log(max(2, magnitude)). This is a value-magnitude model, not complexity in the number of input bits.

Python arbitrary-precision arithmetic, conversion and output-value length are excluded. For example, factorial has O(n) scalar operations and O(1) scalar storage slots in this model; its true Python bit cost and growing integer storage are not claimed to be O(n) time and O(1) bits. No exact elapsed time or byte count is inferred.

## Supported loop patterns

| Counter recurrence | Required entry/bound | Estimate |
|---|---|---|
| i = i + positive constant | Constant start; i < n or i <= n; invariant n | O(n) |
| i = i - positive constant | Input-dependent start; i > constant or i >= constant | O(n) |
| i = i * constant factor >= 2 | Strictly positive constant start; increasing ordered bound n | O(log n) |
| n = n / constant divisor >= 2 | n > nonnegative constant, or n >= positive constant | O(log n) |
| Any supported recurrence with fixed constant bounds | Proven monotonic direction/threshold | O(1) relative to runtime input |
| Independent nested supported loops | Inner counter is unconditionally reset before its loop | Products such as O(n^2), O(m*n), O(n*log n) |

Reversed comparisons are normalized when the actual modified counter is on the right. Step amounts may be literal-only constant expressions, not mutable variables. A loop requires exactly one unconditional assignment to its counter and an invariant bound. The analysis rejects reads/extra writes to the counter and writes to a bound variable anywhere in the body. Abstract dataflow propagates literal constants and input aliases, merges uncertain branches conservatively, and invalidates loop-written values before analyzing nested bodies. This avoids assuming an inner counter is reset merely because it was initialized outside the outer loop.

Sequential costs add and dominated terms are removed. Alternative branches take a conservative upper bound. Constant conditions may exclude unreachable branches. Independent nested factors multiply. These are upper bounds, not claims of tight Theta complexity.

## Unsupported cases

The analyzer reports **Unable to determine** for compound conditions, equality/inequality termination tests, nonlinear/data-dependent updates such as Euclid's remainder recurrence, conditional or multiple counter updates, unknown starts/bounds, dependent nested bounds such as j < i, and thresholds that may prevent termination. It also rejects zero/negative growth starts and division loops with n >= 0. It does not guess O(log n) for GCD or O(sqrt n) for the prime-checker program.

Scalar-space analysis can remain available when time is unresolved. For a fixed Tiny program, the generated VM has finitely many declared storage identities and temporaries, plus a bounded expression stack and no recursion/heap arrays. The result is **O(1) scalar slots**. The report lists actual declared/temporary identity counts, excludes external input/output, IDE trace and compiler buffers, and explicitly leaves bit-level auxiliary space undetermined.

## Evidence

`tests/test_complexity.py` covers constants, linear increasing/decreasing and reversed comparisons, rectangular nesting, separate parameters, logarithmic growth/shrinkage, mixed nesting, constant bounds, shadowing, aliases, ambiguous and nonterminating patterns, invalid compilations, and separation from measured runtime. GUI tests verify that edited source marks the retained estimate stale and that recompile replaces it.
