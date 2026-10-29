# Security and privacy notes

## Security
- Passwords: scrypt (Python standard library) with a random salt; never stored or logged in plain text.
- No default accounts: the first Admin is created on the Welcome screen.
- Lock-out after 5 wrong passwords (5 minutes); auto-lock after inactivity; forced change after an Admin reset.
- Role-based permissions checked in the services (not just hidden buttons).
- Append-only audit log for sign-ins, customer changes, sales, refunds, voids, overrides, exports, deletions,
  imports, settings, camera use, backups and restores. Details never contain passwords or tokens.
- SQL is always parameterised; foreign keys are enforced; money is stored as integers.
- Camera RTSP passwords are masked on screen and in the audit log.

## Backups
Backups contain personal data. Keep them on an encrypted drive (BitLocker / encrypted USB), keep one copy off-site,
do not e-mail them, and delete old copies you no longer need. Restore always validates the file and keeps a safety
copy of the data it replaces.

## Privacy
NomLoyal provides tools; it does not make a store legally compliant by itself. Before going live:
1. Check the data-protection and biometric rules that apply to your store and location.
2. Adapt the privacy notice (Privacy page) and show it to customers before registering them.
3. Register customers only with their consent (the app requires the consent box by default).
4. Collect only what you need; set retention periods; run the clean-up regularly.
5. Give staff the lowest role they need; review the audit log.
6. Answer customer requests from the profile: export, correct, withdraw consent, delete / anonymise.
7. Do not enable biometric recognition without explicit written consent, a documented purpose, a validated
   provider and legal advice. NomLoyal never stores camera footage or face images.
