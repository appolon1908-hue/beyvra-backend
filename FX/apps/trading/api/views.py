from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response

from .errors import error_response


def _disabled(request):
    return error_response(request, "FEATURE_DISABLED", 503)


class OrderCollectionView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request):
        return Response({"results": []})
    def post(self, request):
        return _disabled(request)


class OrderPreviewView(APIView):
    permission_classes = (IsAuthenticated,)
    def post(self, request):
        return _disabled(request)


class OrderDetailView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request, order_id):
        return error_response(request, "RESOURCE_NOT_FOUND", 404)


class OrderCancelView(APIView):
    permission_classes = (IsAuthenticated,)
    def post(self, request, order_id):
        return _disabled(request)


class EmptyCollectionView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request):
        return Response({"results": []})


class EmptyDetailView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request, **kwargs):
        return error_response(request, "RESOURCE_NOT_FOUND", 404)


class FeesView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request):
        return Response({"results": [], "real_trading_enabled": False})
