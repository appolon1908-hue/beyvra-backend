from types import SimpleNamespace

from django.core.management.base import BaseCommand, CommandError

from news_app.service import fetch_newsdata


class Command(BaseCommand):
    help="Run one bounded, governed NewsData ingestion page"

    def add_arguments(self,parser):
        parser.add_argument("--endpoint",choices=("latest","crypto","market","sources"),default="latest")
        parser.add_argument("--limit",type=int,default=10)

    def handle(self,*args,**options):
        if not 1 <= options["limit"] <= 50: raise CommandError("limit must be between 1 and 50")
        request=SimpleNamespace(query_params={"limit":str(options["limit"])},headers={})
        result=fetch_newsdata(request,options["endpoint"])
        self.stdout.write(f"endpoint={options['endpoint']} canonical_results={len(result['results'])} next_cursor_present={bool(result['next_cursor'])}")
