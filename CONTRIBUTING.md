# Contributing to GeoSentinel AI

Thanks for your interest in improving GeoSentinel AI.

## Development setup

1. Fork the repository and create a feature branch.
2. Follow the [local setup instructions](./README.md#installation-and-local-setup).
3. Keep changes focused and explain behavior changes in the pull request.
4. Do not commit credentials, private imagery, generated environment files, or
   large local artifacts.

## Before opening a pull request

Run the checks relevant to your change:

```powershell
# Backend syntax check
python -m compileall backend\app backend\train_model.py

# Frontend production build
cd frontend
npm install
npm run build
```

For changes to image analysis, include a short explanation of the inputs,
thresholds, and expected effect on findings. For API changes, update
[`docs/api-reference.md`](./docs/api-reference.md) and add or update examples.

## Pull requests

- Use a descriptive title and summarize the problem and solution.
- Include screenshots for dashboard or styling changes.
- Mention tests run and any limitations.
- Keep formatting and naming consistent with the existing code.

## Reporting security issues

Do not disclose exploitable vulnerabilities in a public issue. Contact the
repository owner privately with reproduction details and an appropriate
disclosure window.
