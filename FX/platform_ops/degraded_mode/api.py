from django.conf import settings
from rest_framework.response import Response
from rest_framework.views import APIView
from platform_ops.permissions import IsSreViewer
from .resolver import OperationalModeResolver
class ModeView(APIView):
    permission_classes=(IsSreViewer,)
    def get(self,request):
        signals={"global_halt":False,"security_halt":False,"financial_halt":False,"execution_halt":not settings.EXTERNAL_EXECUTION_ENABLED,"dependency_failure":False,"capacity_restriction":False,"data_stale":False}
        return Response({"mode":OperationalModeResolver.resolve(signals),"signals":signals})
