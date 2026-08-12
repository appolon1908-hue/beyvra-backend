from rest_framework.response import Response
from rest_framework.views import APIView
from platform_ops.permissions import IsSreViewer
from .hashes import manifest_root
from .models import OperationalEvidenceManifest
class EvidenceView(APIView):
    permission_classes=(IsSreViewer,)
    def get(self,request,release_id):
        try:x=OperationalEvidenceManifest.objects.prefetch_related("items").get(release_id=release_id)
        except OperationalEvidenceManifest.DoesNotExist:return Response({"code":"NOT_FOUND"},status=404)
        return Response({"release_id":x.release_id,"root_hash":x.root_hash,"integrity":"PASS" if x.root_hash==manifest_root(x) else "FAIL","candidate_hash":x.candidate_hash,"created_at":x.created_at,"items":[{"category":i.category,"artifact_ref":i.artifact_ref,"sha256":i.sha256,"tool_version":i.tool_version,"result":i.result} for i in x.items.all()]})
