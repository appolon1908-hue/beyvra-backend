from rest_framework.response import Response
from rest_framework.views import APIView
from platform_ops.permissions import IsSreViewer
from .models import CapacityProfile
class CapacityView(APIView):
    permission_classes=(IsSreViewer,)
    def get(self,request,service_code=None):
        q=CapacityProfile.objects.filter(status="CERTIFIED"); q=q.filter(service_code=service_code) if service_code else q
        return Response({"capacity":[{"service":x.service_code,"resource_type":x.resource_type,"tested_limit":str(x.tested_limit),"safe_operating_limit":str(x.safe_operating_limit),"unit":x.unit,"test_sha":x.test_sha,"tested_at":x.tested_at} for x in q]})
