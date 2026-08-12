from django.conf import settings
from rest_framework.response import Response
from rest_framework.views import APIView
from platform_ops.permissions import IsSreViewer
from .models import FeatureFlagDefinition
from .evaluator import inspect
class FeatureFlagsView(APIView):
    permission_classes=(IsSreViewer,)
    def get(self,request):
        rows=[]
        for x in FeatureFlagDefinition.objects.all():
            state=inspect(x.code,getattr(settings,x.code,None))
            rows.append({"code":x.code,"enabled":state["effective_enabled"],"configured_valid":state["configured_valid"],"unsafe_configuration":state["unsafe_configuration"],"fail_closed":state["fail_closed"],"risk_class":x.risk_class,"owner":x.owner,"expires_at":x.expires_at,"version":x.version})
        return Response({"feature_flags":rows,"unsafe_configuration_count":sum(1 for row in rows if row["unsafe_configuration"])})
