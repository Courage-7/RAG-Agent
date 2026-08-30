# Dataset contract

Datasets will use versioned JSONL. Each record will have a stable case ID, split, workspace fixture, query, expected behavior, permitted evidence identifiers, prohibited evidence identifiers, reference facts, tags, and metric-specific thresholds. Provider outputs and generated answers are run artifacts, not source labels.

The initial 100–200 reviewed cases are intentionally not fabricated during scaffolding; they require a representative corpus and domain owners.
