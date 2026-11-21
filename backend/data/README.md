# Backend data

This directory contains CSV recovery history and local runtime data. The
tracked `scans.csv` and `findings.csv` are fallbacks; Neo4j remains the primary
durable store. The `live/`, `evidence/`, and training-data outputs are local
artifacts and may be ephemeral in deployment.

Do not place credentials or private imagery here. See
[`docs/data-model.md`](../../docs/data-model.md) for record and storage
formats.
