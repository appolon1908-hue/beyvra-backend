import json
from django.core.management.base import BaseCommand, CommandError
from apps.trading.reconciliation import SCOPES, run

class Command(BaseCommand):
    help="Run read-only simulated-trading reconciliation and optionally persist immutable evidence"
    def add_arguments(self,parser):
        parser.add_argument("--scope",choices=sorted(SCOPES),default="full"); parser.add_argument("--tenant")
        parser.add_argument("--format",choices=("human","json"),default="human"); parser.add_argument("--no-persist",action="store_true")
    def handle(self,*_args,**options):
        report=run(scope=options["scope"],tenant=options["tenant"],persist=not options["no_persist"])
        if options["format"]=="json": self.stdout.write(json.dumps(report,sort_keys=True))
        else:
            self.stdout.write(f"RECONCILIATION={report['status']}\nRUN_ID={report['run_id'] or 'NOT_PERSISTED'}\nCHECKS={len(report['checks'])}\nVIOLATIONS={len(report['violations'])}")
            for check in report["checks"]: self.stdout.write(f"{check['code']}={check['status']}")
        if report["status"]!="PASS": raise CommandError("RECONCILIATION_FAILED")
