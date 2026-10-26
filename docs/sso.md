# Single sign-on (not yet enabled)

Build 1 uses local username/password accounts for development on fictional data.

When K-State IT approves single sign-on (Shibboleth/SAML through the eID, or Entra ID):

1. Add the chosen adapter package (`python3-saml` or `django-allauth[saml]`) to `pyproject.toml` and the Dockerfile.
2. Configure it in `config/settings/base.py` under the `SSO_ENABLED` block: entity ID, metadata URL, attribute mapping (eID → `username`, mail → e-mail, givenName/sn → first and last name).
3. Map the SSO identity to a `User` by e-mail against `person_emails`; create the `User` for a matched `Person` on first login. People who are not on the roster get no account.
4. Set `SSO_ENABLED=true` in `.env`; the login page then shows the SSO button and hides the password form. Local passwords stay available to superusers for break-glass access.

Nothing else in the application changes: permissions, roles and data access are independent of how the user authenticated.
