# Recruiting Pipeline Starter

This workspace contains a small Python starter for the recruiting pipeline described in the project summary.

## What is included

- `app/services.py`: core candidate/job logic
  - resume fingerprinting
  - deduplication
  - candidate ranking
- `tests/test_services.py`: sample tests covering core functionality

## Run the tests

```bash
python -m pytest -q
```

## Notes

This is intentionally a lightweight starter implementation. It does not yet integrate with Microsoft Graph, LinkedIn, or a database, but it gives you a testable foundation for the ingestion and matching workflow.
