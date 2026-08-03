# Virtual demo ledger

Demo accounts are isolated from `wallet.Wallet`, payments, withdrawals, transfers, and real-money ledgers. The only automatic entry is `DEMO_INITIAL_CREDIT`, exactly `200000` integer cents (`$2,000.00 USD`), protected by unique account and reference constraints. Balance is presented as virtual funds and is never caller-editable.
