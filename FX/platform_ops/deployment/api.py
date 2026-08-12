from rest_framework.response import Response
from rest_framework.views import APIView
from platform_ops.permissions import IsSreViewer
from .models import DeploymentPlan
class DeploymentView(APIView):
    permission_classes=(IsSreViewer,)
    def get(self,request):return Response({"deployments":[{"id":x.id,"release_id":x.release_id,"environment":x.environment,"strategy":x.strategy,"state":x.state,"created_at":x.created_at} for x in DeploymentPlan.objects.order_by("-created_at")[:100]]})
