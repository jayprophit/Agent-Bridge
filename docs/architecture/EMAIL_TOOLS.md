# Email Tools (v0.8, Part E)

Canonical: email.compose/draft/reply (local, artifact-backed, real
EmailAdapter) and email.read/search/send (PROVIDER_REQUIRED until an
SMTP/IMAP/OAuth/plugin provider is configured). Sending is an EXTERNAL side
effect: owner-only profile + explicit approval + configured provider, all
three. Automated tests never send real email.
