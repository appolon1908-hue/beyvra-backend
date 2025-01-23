from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response
#from django.shortcuts import render
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from .serializers import DashboardMetricsSerializer
from .utils import get_or_set_metrics_cache
from rest_framework.permissions import AllowAny
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

@extend_schema(
    description='Get dashboard metrics',
    parameters=[
        OpenApiParameter(
            name='categories_filters',
            type=OpenApiTypes.STR,
        ),
        OpenApiParameter(
            name='start_date',
            type=OpenApiTypes.STR,
        ),
        OpenApiParameter(
            name='end_date',
            type=OpenApiTypes.STR,
        ),
    ],
    request=DashboardMetricsSerializer,
    responses={200: 'Success', 400: 'Bad Request'},
)
@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([AnonRateThrottle, UserRateThrottle])
def dashboard_metrics(request):
    serializer = DashboardMetricsSerializer(data=request.data)

    if serializer.is_valid():
        categories_filters = serializer.validated_data.get('categories_filters', None)
        start_date = serializer.validated_data.get('start_date', None)
        end_date = serializer.validated_data.get('end_date', None)

        metrics_data = get_or_set_metrics_cache(request.get_full_path(), start_date, end_date, categories_filters)

        return Response(metrics_data, status=status.HTTP_200_OK)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
