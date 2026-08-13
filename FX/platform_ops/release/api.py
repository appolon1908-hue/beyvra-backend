from rest_framework.response import Response
from rest_framework.views import APIView
from platform_ops.permissions import IsSreViewer
from .models import ReleaseManifest
def row(x):return {"release_id":x.release_id,"backend_sha":x.backend_sha,"frontend_sha":x.frontend_sha,"financial_service_sha":x.financial_service_sha,"image_digests":x.image_digests,"migration_hash":x.migration_hash,"openapi_hash":x.openapi_hash,"sbom_hash":x.sbom_hash,"configuration_hash":x.configuration_hash,"state":x.state,"created_at":x.created_at}
class ReleaseView(APIView):
    permission_classes=(IsSreViewer,)
    def get(self,request,release_id=None):
        if release_id:
            try:return Response(row(ReleaseManifest.objects.get(release_id=release_id)))
            except ReleaseManifest.DoesNotExist:return Response({"code":"NOT_FOUND"},status=404)
        x=ReleaseManifest.objects.order_by("-created_at").first();return Response({"release":row(x) if x else None})
