# Historical test fixture

`v4_nf_pre_fix.py` is the exact byte sequence of
`grounding/verifiers_v4.py` at commit
`1106c2b536b19b311c57e006b7554a5d6d64c2af`. Its Git blob, SHA-256 and size
are recorded in `v4_nf_pre_fix.provenance.json`; the regression test also
pins the commit and SHA-256 independently.

It is used only by
`test_benchmark_v4_nf.NFOccurrenceRunnerTests.test_old_and_current_module_globals_are_isolated`.
The test proves the old and current implementations have isolated module globals
and retain their different non-factual occurrence-accounting behavior. It reads
this single fixture instead of invoking `git show`, so the test works in a
shallow clone or exported source tree without Git history.

This is not a production backend or a new source snapshot tree. Do not edit the
historical bytes or substitute the current module; update the test explicitly if
its historical comparison ever changes.
