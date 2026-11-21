# Database integration

This package initializes the Neo4j driver and creates the graph schema.
[`neo4j.py`](./neo4j.py) owns connection configuration and lifecycle;
[`schema.py`](./schema.py) defines constraints and indexes.

Neo4j is the primary durable store. CSV recovery behavior is implemented
outside this package. Configure database settings through environment
variables and never commit credentials.
