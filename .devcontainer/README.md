# Testing the CNAP Reporting Hub in GitHub Codespaces

This folder starts a private test copy of the Hub with fictional data and the redesign turned on.
It is for trying the site only, never for real CNAP data.

1. On the repository page, choose Code, then Codespaces, then "Create codespace on main".
2. Wait for the setup to finish (a few minutes the first time).
3. The site opens in a new browser tab. If it doesn't, open the Ports tab and select the address beside "CNAP Reporting Hub".
4. Sign in with any fictional account below. Every account uses the password Demo-Password-2026.
5. Use the "Design preview" switch at the bottom of each page to compare the current design with the redesign.

Fictional accounts:

| Username | Who |
|---|---|
| mwills | Evaluator, full administrator access |
| okafor | Pilot Project Leader |
| brandt | Research Project Leader |
| varga | Core Director |
| adeyemi | Pilot Project Leader |
| lindqvist | Core user |

## Letting someone without a GitHub account use it

1. Start the codespace as above.
2. Open the Ports tab, right-click "CNAP Reporting Hub," and choose Port Visibility, then Public.
3. Copy the address and send it, with a fictional username and the password.

The address works only while your codespace is running.
A codespace stops after 30 minutes without use; you can raise that to 4 hours at github.com/settings/codespaces.

Emails, including sign-in links, print in the Codespace terminal instead of being sent.
When you finish, stop the codespace from github.com/codespaces, so it doesn't use your free hours.
