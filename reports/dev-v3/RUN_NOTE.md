# Interrupted provider-compatibility run

This initial v3 development run was stopped after repeated HTTP 400 responses in the v3 verification stage. Extraction succeeded. A separate small request confirmed the provider rejected JSON-object mode because the messages did not contain the word `json`. The v3 verification and merge prompts described a JSON-shaped object but omitted that literal mode requirement.

This is an API request compatibility defect, not a semantic quality result. Completed per-case records, usage and the original run configuration remain intact. The report was checkpointed as `interrupted` from the saved records after terminating the process. Any in-flight call at termination may have unreported usage; recorded cost is not a complete billing total.

The correction explicitly requests JSON in those two prompts and adds a provider-contract regression test. It does not change the claim granularity, merge criteria, conflict semantics, gold data or scoring. A new run directory is used for the corrected implementation. The original code hash snapshot in `reports/v3-code-freeze.json` is retained and superseded by a later snapshot; neither snapshot is a formal confirmation-set approval.
