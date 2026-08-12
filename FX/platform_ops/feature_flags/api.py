from django.conf import settings
from rest_framework.response import Response
from rest_framework.views import APIView
from platform_ops.permissions import IsSreViewer
from .models import FeatureFlagDefinition
from .evaluator import evaluate
class FeatureFlagsView(APIView):
    permission_classes=(IsSreViewer,)
    def get(self,request):return Response({"feature_flags":[{"code":x.code,"enabled":evaluate(x.code,getattr(settings,x.code,None)),"risk_class":x.risk_class,"owner":x.owner,"expires_at":x.expires_at,"version":x.version} for x in FeatureFlagDefinition.objects.all()]})
