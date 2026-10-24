# Operational audit: recovered bidirectional M1 pilot

Audit date: 2026-10-24 (Asia/Shanghai). Read-only operational checks; no model calls, semantic scoring, prompt edits, or case revisions were performed by this audit.

## Result

PASS for the recorded experiment and append-only recovery. The final journal contains 152 unique requested identities: all original 50 records preserved byte for byte, plus exactly 102 newly reserved single-attempt calls. All 44 generic/bidirectional pairs received byte-equivalent structured payloads. The original aborted run remains hash-identical. An original started counter exceeds its journal by one; whether that missing attempt reached the provider is unknown. Therefore 152 is the number of recorded attempts, not an established exact count of all physical provider requests.

## Checks

- Original freeze, every bound inference/source/data/plan file, prompt hashes, recovery amendment files, original-run files and final journal hash match their manifests.
- Each recorded identity appears exactly once. Existing errors are retained; no journaled attempt was rerun. Every new record has a unique prior fsync reservation with matching prompt/payload hashes.
- Reconstructed every payload solely from the frozen answer plus its permitted draft and validator diagnostic. Model messages exactly match these payloads and their frozen system prompt. No case ID, seed kind, family, language or expected-answer metadata was added by the runner.
- Every record has exactly one provider trace with attempt=1, thinking=disabled and max_output_tokens=8192. Frozen settings retain upstream_retries=0 and repair_attempts=0.
- Every per-case sequence follows the preregistered order and completes one step before the next begins. All positions are included below; the reused runtime helper’s legacy first/second-order view omits positions 2 and 3 and must not be treated as a full order analysis.
- `git diff e78fa35 -- grounding configs prompts` is empty: production inference remains unchanged.

## Interpretation limits

- Structural `error` is not a semantic omission, non-factual determination, or production completion failure. Initial-stage validation excludes production fallback/review behavior. Separate valid semantic omissions from technically unserved targets.
- Claim counts and exact span coverage do not establish fact-selection correctness. Semantic scoring belongs to the separate blinded review.
- Recorded-call cost calculations reproduce the frozen accounting helper. A non-null `estimated_total` applies only to the 152 recorded calls; the original unjournaled started-counter overhead remains unknown and unpriced.
- Generic/bidirectional chain costs each include the shared base for fair hypothetical deployment comparison. Do not sum those chain totals to claim physical experiment spending. Advisory Gemini usage is separate.
- The reused runtime helper’s `summary_totals.extracted_claim_count=0` is a telemetry-layout artifact: this pilot stores validated extraction directly in each record rather than the production `telemetry.extraction` field. Use per-arm analysis `claim_count`; do not interpret the legacy zero as factless outputs.
- All 152 calls omit separate reasoning-token accounting (`reasoning_usage_complete=false`). The request explicitly disables thinking, but the helper’s zero must not be presented as measured zero reasoning tokens. Prompt and completion usage are fully reported.
- Natural and controlled subsets are not pooled. Controlled examples reuse original answers, and two repetitions do not double the number of independent natural answers.
- This was an interrupted run recovered under a frozen infrastructure amendment. It is not a pristine uninterrupted run or untouched held-out benchmark.

## Machine-checked operational details

```json
{
  "frozen_hash": "08b94eaa6ed2b52bc2d3d60bbc8483327e3b630660073f92f1330c4255045ebc",
  "recovery_hash": "a9edfbec0109f51c3343a00e2d03fad78485cbd67f37b6d33b460e6cd54b690a",
  "responses_hash": "cc3108351dc7bc3c5fb7a1806e2c3bbb48ad86c0f642b997f8f5002fd0ea5478",
  "original_hash": "26bbb975f34dee4ecab4733bec41a4d113dd3783bc6a2c0776aca711bdeb625c",
  "original_records": 50,
  "new_records": 102,
  "recorded_attempts": 152,
  "unknown_old_started": 1,
  "provider_attempts_exact": null,
  "same_input_pairs": 44,
  "files_bound": 53,
  "progress_replace_fallbacks": 0,
  "order_counts": {
    "natural": {
      "base": {
        "0": 32
      },
      "bidirectional": {
        "1": 11,
        "2": 11,
        "3": 10
      },
      "fresh": {
        "1": 10,
        "2": 11,
        "3": 11
      },
      "generic": {
        "1": 11,
        "2": 10,
        "3": 11
      }
    },
    "controlled": {
      "bidirectional": {
        "0": 6,
        "1": 6
      },
      "generic": {
        "0": 6,
        "1": 6
      }
    }
  },
  "position_timing": {
    "natural": {
      "0": {
        "n": 32,
        "mean_seconds": 1.7860937499899592,
        "p95_seconds": 3.047000000020489
      },
      "1": {
        "n": 32,
        "mean_seconds": 1.7803749999875436,
        "p95_seconds": 2.51500000001397
      },
      "2": {
        "n": 32,
        "mean_seconds": 1.7445624999963911,
        "p95_seconds": 2.640999999945052
      },
      "3": {
        "n": 32,
        "mean_seconds": 1.737875000013446,
        "p95_seconds": 2.515999999945052
      }
    },
    "controlled": {
      "0": {
        "n": 12,
        "mean_seconds": 1.8997499999920062,
        "p95_seconds": 2.937999999965541
      },
      "1": {
        "n": 12,
        "mean_seconds": 1.7928333333596431,
        "p95_seconds": 2.859000000054948
      }
    }
  },
  "errors": {
    "natural/base": {
      "valid": 24,
      "error": 8,
      "finish_reasons": {
        "stop": 32
      },
      "http_statuses": {
        "200": 32
      },
      "failure_categories": {
        "meaningful_answer_coverage_gap": 8
      }
    },
    "natural/bidirectional": {
      "valid": 31,
      "error": 1,
      "finish_reasons": {
        "stop": 32
      },
      "http_statuses": {
        "200": 32
      },
      "failure_categories": {
        "meaningful_answer_coverage_gap": 1
      }
    },
    "natural/fresh": {
      "valid": 24,
      "error": 8,
      "finish_reasons": {
        "stop": 32
      },
      "http_statuses": {
        "200": 32
      },
      "failure_categories": {
        "meaningful_answer_coverage_gap": 6,
        "non_factual_span_occurrence_or_order": 2
      }
    },
    "natural/generic": {
      "valid": 29,
      "error": 3,
      "finish_reasons": {
        "stop": 32
      },
      "http_statuses": {
        "200": 32
      },
      "failure_categories": {
        "meaningful_answer_coverage_gap": 3
      }
    },
    "controlled/bidirectional": {
      "valid": 12,
      "error": 0,
      "finish_reasons": {
        "stop": 12
      },
      "http_statuses": {
        "200": 12
      },
      "failure_categories": {}
    },
    "controlled/generic": {
      "valid": 12,
      "error": 0,
      "finish_reasons": {
        "stop": 12
      },
      "http_statuses": {
        "200": 12
      },
      "failure_categories": {}
    }
  },
  "runtime": {
    "by_variant_execution_order": {
      "first": {
        "mean_latency_seconds": 1.8170909090814265,
        "p95_latency_seconds": 2.937999999965541,
        "record_count": 44,
        "reference_cost": {
          "cache_standardized_all_miss_known_subtotal": 0.019552200000000006,
          "cache_standardized_all_miss_total": 0.019552200000000006,
          "cache_standardized_priced_calls": 44,
          "cache_standardized_unpriced_calls": 0,
          "complete": true,
          "estimated_total": 0.013907988000000001,
          "known_usage_subtotal": 0.013907988000000001,
          "note": "Fixed reference prices, not provider billing. Unpriced calls are excluded from subtotals. All-miss pricing holds cache treatment constant; it is not an actual bill.",
          "priced_calls": 44,
          "reference_prices": {
            "cached_input_per_million": 0.006,
            "currency": "USD",
            "input_per_million": 0.3,
            "output_per_million": 1.2
          },
          "unpriced_calls": 0
        },
        "usage": {
          "cache_accounted_calls": 44,
          "cache_usage_complete": true,
          "calls": 44,
          "calls_with_usage": 44,
          "completion_tokens": 8513,
          "prompt_cache_hit_tokens": 19198,
          "prompt_cache_miss_tokens": 11924,
          "prompt_tokens": 31122,
          "reasoning_accounted_calls": 0,
          "reasoning_tokens": 0,
          "reasoning_usage_complete": false,
          "total_tokens": 39635,
          "usage_complete": true
        }
      },
      "second": {
        "mean_latency_seconds": 1.7837727272708435,
        "p95_latency_seconds": 2.51500000001397,
        "record_count": 44,
        "reference_cost": {
          "cache_standardized_all_miss_known_subtotal": 0.02371170000000001,
          "cache_standardized_all_miss_total": 0.02371170000000001,
          "cache_standardized_priced_calls": 44,
          "cache_standardized_unpriced_calls": 0,
          "complete": true,
          "estimated_total": 0.015733716,
          "known_usage_subtotal": 0.015733716,
          "note": "Fixed reference prices, not provider billing. Unpriced calls are excluded from subtotals. All-miss pricing holds cache treatment constant; it is not an actual bill.",
          "priced_calls": 44,
          "reference_prices": {
            "cached_input_per_million": 0.006,
            "currency": "USD",
            "input_per_million": 0.3,
            "output_per_million": 1.2
          },
          "unpriced_calls": 0
        },
        "usage": {
          "cache_accounted_calls": 44,
          "cache_usage_complete": true,
          "calls": 44,
          "calls_with_usage": 44,
          "completion_tokens": 8469,
          "prompt_cache_hit_tokens": 27136,
          "prompt_cache_miss_tokens": 18027,
          "prompt_tokens": 45163,
          "reasoning_accounted_calls": 0,
          "reasoning_tokens": 0,
          "reasoning_usage_complete": false,
          "total_tokens": 53632,
          "usage_complete": true
        }
      }
    },
    "error_codes": {
      "invalid_model_output": 20
    },
    "mean_latency_seconds": 1.7754999999987806,
    "p95_latency_seconds": 2.702999999979511,
    "record_count": 152,
    "reference_cost": {
      "cache_standardized_all_miss_known_subtotal": 0.07622040000000001,
      "cache_standardized_all_miss_total": 0.07622040000000001,
      "cache_standardized_priced_calls": 152,
      "cache_standardized_unpriced_calls": 0,
      "complete": true,
      "estimated_total": 0.05112162000000003,
      "known_usage_subtotal": 0.05112162000000003,
      "note": "Fixed reference prices, not provider billing. Unpriced calls are excluded from subtotals. All-miss pricing holds cache treatment constant; it is not an actual bill.",
      "priced_calls": 152,
      "reference_prices": {
        "cached_input_per_million": 0.006,
        "currency": "USD",
        "input_per_million": 0.3,
        "output_per_million": 1.2
      },
      "unpriced_calls": 0
    },
    "returned_models": {
      "deepseek-flash": 152
    },
    "returned_system_fingerprints": {
      "e72d3c7f663d3e1383b00b3884cb4501": 152
    },
    "stage_calls": {
      "controlled_bidirectional": 12,
      "controlled_generic": 12,
      "natural_base": 32,
      "natural_bidirectional": 32,
      "natural_fresh": 32,
      "natural_generic": 32
    },
    "summary_totals": {
      "extracted_claim_count": 0,
      "fallback_claim_count": 0,
      "non_factual_span_count": 0
    },
    "usage": {
      "cache_accounted_calls": 152,
      "cache_usage_complete": true,
      "calls": 152,
      "calls_missing_cache_accounting": 0,
      "calls_missing_usage": 0,
      "calls_with_usage": 152,
      "completion_tokens": 29132,
      "prompt_cache_hit_tokens": 85370,
      "prompt_cache_miss_tokens": 52170,
      "prompt_tokens": 137540,
      "reasoning_accounted_calls": 0,
      "reasoning_tokens": 0,
      "reasoning_usage_complete": false,
      "total_tokens": 166672,
      "usage_complete": true
    }
  },
  "chain_reference_costs": {
    "generic": {
      "reference_prices": {
        "input_per_million": 0.3,
        "cached_input_per_million": 0.006,
        "output_per_million": 1.2,
        "currency": "USD"
      },
      "known_usage_subtotal": 0.020993892000000004,
      "estimated_total": 0.020993892000000004,
      "priced_calls": 64,
      "unpriced_calls": 0,
      "complete": true,
      "cache_standardized_all_miss_known_subtotal": 0.0305142,
      "cache_standardized_all_miss_total": 0.0305142,
      "cache_standardized_priced_calls": 64,
      "cache_standardized_unpriced_calls": 0,
      "note": "Fixed reference prices, not provider billing. Unpriced calls are excluded from subtotals. All-miss pricing holds cache treatment constant; it is not an actual bill."
    },
    "bidirectional": {
      "reference_prices": {
        "input_per_million": 0.3,
        "cached_input_per_million": 0.006,
        "output_per_million": 1.2,
        "currency": "USD"
      },
      "known_usage_subtotal": 0.021163908000000002,
      "estimated_total": 0.021163908000000002,
      "priced_calls": 64,
      "unpriced_calls": 0,
      "complete": true,
      "cache_standardized_all_miss_known_subtotal": 0.0311358,
      "cache_standardized_all_miss_total": 0.0311358,
      "cache_standardized_priced_calls": 64,
      "cache_standardized_unpriced_calls": 0,
      "note": "Fixed reference prices, not provider billing. Unpriced calls are excluded from subtotals. All-miss pricing holds cache treatment constant; it is not an actual bill."
    }
  },
  "chain_allmiss_ratio": 1.0203708437383252
}
```
