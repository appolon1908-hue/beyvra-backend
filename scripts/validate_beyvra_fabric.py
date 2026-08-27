#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
contract = json.loads((ROOT / 'contracts/automation/beyvra-fabric.v2.json').read_text())
assert contract['workflow_family'] == 'product.beyvra-nonfinancial'
assert contract['allowed_command_prefixes'] == ['beyvra.operations.']
assert contract['direct_n8n_backend_access'] is False
assert contract['direct_n8n_database_access'] is False
assert contract['direct_browser_n8n_access'] is False
assert all(value is False for value in contract['capabilities'].values())
for prefix in ('trade.','order.','wallet.','ledger.','payment.','withdrawal.','custody.','chain.'):
    assert prefix in contract['prohibited_command_prefixes']
print('BEYVRA_INTEGRATION_FABRIC_V2=PASS')
