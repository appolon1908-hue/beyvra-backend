# Statement authority

A statement is issuable only after reconciliation passes. Simulation statements are clearly labeled. A real statement requires Financial Service authority; this repository never reads its database directly. Issued statements are immutable at both the Django model and PostgreSQL trigger layers. Corrections create a higher version referencing the superseded statement with reason and timestamp. Artifacts are private and downloads require owner/tenant authorization through short-lived references.
