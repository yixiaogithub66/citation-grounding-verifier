# Cost convention for the recorded runs

Source: [DeepSeek model pricing](https://api-docs.deepseek.com/quick_start/pricing/), checked on 2026-10-20. The selected model is `deepseek-flash`.

All recorded runs use the same **peak tariff reference** in USD per million tokens:

| Token category | Reference rate |
| --- | ---: |
| Input, cache miss | 0.30 |
| Input, cache hit | 0.006 |
| Output, including provider-counted reasoning tokens | 1.20 |

The benchmark reads actual cache-hit/cache-miss counters from each successful upstream response and adds every call, including repair attempts. Missing usage is marked incomplete, not assumed zero. Local baseline model-token cost is zero; local compute is not priced.

The amount is a standardized estimate, **not a billing statement**. DeepSeek's published off-peak tariff can be lower; time-of-day discounts, grants and later price changes are not inferred. Using one reference tariff makes the methods' token consumption comparable even if runs cross a billing time window. No separate charge is added for reasoning tokens already included in `completion_tokens`.
