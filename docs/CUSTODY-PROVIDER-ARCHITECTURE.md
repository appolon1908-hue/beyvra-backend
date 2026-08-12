# Custody provider architecture

`CustodyProvider` covers deposit destination, balance/deposit lookup, withdrawal validation/submission/lookup, and supported cancellation. Beyvra policy remains responsible for KYC/AML, limits, destination security, step-up, maker/checker, and kill switches.

Custody responses never bypass Financial Service or reconciliation. BitGo is a candidate requiring legal, license, security, compliance, financial, credential-owner, staging, and production approval. Activation is `NO`.

