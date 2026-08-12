from rest_framework.response import Response
from rest_framework.views import APIView
from platform_ops.permissions import IsSreViewer
from .models import SloDefinition
from .services import ErrorBudgetService


class SlosView(APIView):
    permission_classes=(IsSreViewer,)
    def get(self,request,code=None):
        qs=SloDefinition.objects.filter(status="ACTIVE").select_related("sli"); qs=qs.filter(code=code) if code else qs
        rows=[{"code":x.code,"service":x.sli.service_code,"metric_type":x.sli.metric_type,"target":str(x.target),"comparison":x.comparison,"window_seconds":x.window.total_seconds(),"version":x.version} for x in qs]
        if code and not rows:return Response({"code":"NOT_FOUND"},status=404)
        return Response({"slos":rows})


class ErrorBudgetsView(APIView):
    permission_classes=(IsSreViewer,)
    def get(self,request):return Response({"error_budgets":ErrorBudgetService.all()})
