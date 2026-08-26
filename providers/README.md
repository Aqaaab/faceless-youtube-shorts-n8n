# Provider extension point

Add a provider here only when it has been verified as usable.

Required adapter shape:

- `name`: stable identifier
- `capabilities`: explicit capabilities
- `base_url_env`: environment variable name
- `api_key_env`: environment variable name
- `healthcheck`: endpoint or callable
- `enabled`: false until verified
- `healthy`: false until a live check passes

The production workflow must never call these adapters directly. Odysseus remains the only AI boundary.
