import requests
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
import logging


logger = logging.getLogger(__name__)

# Create your views here.


class SetThresholdView(APIView):
   permission_classes = [AllowAny]
   def post(self, request, *args, **kwargs):
        logger.info("YEah")
        return None