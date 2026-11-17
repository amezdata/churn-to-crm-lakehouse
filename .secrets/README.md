# Local secrets

This directory does not version credentials. Locally it may contain:

```
.secrets/pii_hmac_secret
```

That file (or the `PII_HMAC_SECRET` environment variable) holds the HMAC-SHA256 key used to pseudonymize the STEMStar extracts. Without it the same tokens cannot be regenerated. The value is not part of this repository.
