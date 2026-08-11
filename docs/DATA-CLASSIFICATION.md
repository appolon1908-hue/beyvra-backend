# Data classification

PUBLIC is explicitly publishable. INTERNAL is non-customer operational material. CONFIDENTIAL includes contact, support, device, network, and account metadata. RESTRICTED includes password hashes, tokens, KYC/AML, financial records, identity documents, tax IDs, secrets, and audit evidence.

Use opaque references and hashes instead of duplicated raw identifiers. Metrics must never label user, account, email, case, report, or transaction IDs. Sensitive reads record actor, resource class, action, time, and reason—not record contents.
