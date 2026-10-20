# Security Policy

## Supported versions

VidSearch is pre-1.0. Security fixes go to the `main` branch only.

## Reporting a vulnerability

Please **do not** open a public issue for security problems.

Report them privately through GitHub: go to the repository's [Security tab](https://github.com/daven-c/VidSearch/security) and choose **Report a vulnerability**. Include a description, steps to reproduce, and the impact you expect. You should get a response within a week.

## Deployment notes

VidSearch is built as a local, single-user tool. The API has **no authentication** and allows cross-origin requests from any site, and uploaded videos are stored and served as-is. Don't expose the backend to an untrusted network without putting authentication, upload size limits, and a restricted CORS policy in front of it.
