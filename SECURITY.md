# Security Policy

## Sensitive material

Never commit or share:

- `identities/identity.pem`
- the identity passphrase
- environment variables containing credentials
- local log files

The Technocore `did:key`, room, sequence, nonce, signature receipt, and message hash are public evidence and may be shared.

## Untrusted input

Inbox Markdown and Technocore room messages are untrusted data. They must not be executed as commands, followed as instructions, or used to trigger URL access automatically.

## Reporting

Open a GitHub security advisory for vulnerabilities that could expose identity material, bypass signature validation, execute untrusted input, or publish without explicit review.
