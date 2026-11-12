| run | start UTC | exec_match | control | cost/q USD | latency p50 s |
|---|---|---|---|---|---|
| baseline | 12:30 | 0.8333 | 1.0000 | 0.000305 | 1.016 |
| baseline-2 | 12:31 | 0.8333 | 1.0000 | 0.000300 | 0.975 |
| baseline-3 | 12:33 | 0.8667 | 1.0000 | 0.000302 | 0.979 |
| post-fault | 12:35 | 0.4000 | 1.0000 | 0.000302 | 0.999 |
| impl-rvl87f3-schema-renames-1 | 12:38 | 0.8333 | 1.0000 | 0.000321 | 0.978 |
| impl-rvl87f3-renames-casing-nofilter-2 | 12:39 | 0.9167 | 1.0000 | 0.000328 | 1.009 |
| verifier-rvl-87f3dbe9-iter1 | 12:42 | 0.9000 | 0.9500 | 0.000330 | 0.991 |
| impl-rvl87f3-iter2-ties-1 | 12:45 | 0.8833 | 0.9500 | 0.000347 | 1.003 |
| impl-rvl87f3-iter2-head-recheck-2 | 12:47 | 0.9167 | 1.0000 | 0.000329 | 1.023 |
| verifier-rvl-87f3dbe9-iter2 | 12:49 | 0.9000 | 0.9500 | 0.000329 | 1.024 |
| impl-rvl87f3-iter3-superl-1 | 12:52 | 0.9333 | 1.0000 | 0.000346 | 1.080 |
| impl-rvl87f3-iter3-superl-2 | 12:53 | 0.9333 | 1.0000 | 0.000349 | 1.022 |
| verifier-rvl-87f3dbe9-iter3 | 12:56 | 0.9333 | 1.0000 | 0.000351 | 1.047 |
| impl-rvl-d42b3a50-iter1-general-prompt | 12:59 | 0.3833 | 0.9500 | 0.000339 | 1.156 |
| impl-rvl-d42b3a50-iter1-general-prompt-v2 | 13:01 | 0.3833 | 0.9500 | 0.000335 | 1.148 |
| verifier-rvl-d42b3a50-iter1 | 13:03 | 0.3833 | 0.9500 | 0.000332 | 1.163 |

| oracle label | exec_match |
|---|---|
| baseline | 0.8500 |
| post-fault | 0.4000 |
| run-b-notes-only | 0.8500 |
| run-b | 0.9000 |
| run-c | 0.3833 |
