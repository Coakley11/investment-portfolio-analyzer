# Investment AMI — intent-first routing and audit log

## Router version

`MODE_ROUTER_VERSION` is **`p5-intent-v1`**. Deploy verification: `solver_build_id` **`investment-ami-p5-intent-v1`**.

## Flow

1. **Legacy phrase hint** (`detect_investment_send_intent`) — evidence only, not the final decision.
2. **`classify_routing_intent`** — scores reasoning/judgment vs quantitative signals (`intent-v1`).
3. **Structured rules** — objective metrics, historical scenarios, analytical tags, legacy deterministic intents, portfolio context defaults.

**Principle:** reasoning, judgment, comparison, historical critique → **analytical synthesis**; sliders, metrics, overlap, sector %, tax math → **deterministic engines**.

**Starter questions** (`INVESTMENT_AMI_STARTER_QUESTIONS`) stay on the **fast deterministic** path for consistent first-run UX.

## Routing audit

Each Investment AMI submit appends a record via `record_investment_routing_audit`:

| Field | Meaning |
| --- | --- |
| `question` | Original user text |
| `intent_classification` | Classifier snapshot (scores, signals, `prefer_synthesis`) |
| `matched_routing_rules` | Rules that fired |
| `selected_engine` | Engine id or `analytical_synthesis` |
| `synthesis_invoked` | Synthesis ran (enabled, no disable error) |
| `solver_build_id` | Instant solver build |
| `latency_ms` / `token_usage` | From synthesis diagnostics when present |

Session ring buffer: `_ami_routing_audit_log_v1` (last 50). Dev sidebar **AMI reasoning laboratory** shows the last entry and recent log.

Optional local JSONL collection:

```bash
set INVESTMENT_ROUTING_AUDIT_PERSIST=1
```

Appends to `docs/eval/routing_audit.jsonl` (gitignored in production use).
