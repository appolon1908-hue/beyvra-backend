from rest_framework.response import Response
from rest_framework.views import APIView
from platform_ops.permissions import IsSreViewer
from .models import ConfigurationDefinition
from .drift import safe_definition
class ConfigurationView(APIView):
    permission_classes=(IsSreViewer,)
    def get(self,request):return Response({"configuration":[safe_definition(x) for x in ConfigurationDefinition.objects.all()]})
