from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import Transaction, Revenue, UserActivity, Trade, Report
from django.db.models import Sum
#from django.shortcuts import render
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from .serializers import DashboardMetricsSerializer
from datetime import date, timedelta

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
@api_view(['GET'])
def dashboard_metrics(request):
    serializer = DashboardMetricsSerializer(data=request.data)

    if serializer.is_valid():
        
        categories_filters = serializer.validated_data.get('categories_filters', None)
        start_date = serializer.validated_data.get('start_date', None)
        end_date = serializer.validated_data.get('end_date', None)



        return Response({}, status=status.HTTP_200_OK)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


    # Fetch key metrics (aggregated from database or cache)
    '''
    data = {
        "transactions": Transaction.objects.aggregate(Sum('amount')),
        "revenue": Revenue.objects.aggregate(Sum('amount')),
        "transaction_volumes": Transaction.objects.count(),
        "user_activity": UserActivity.objects.filter(is_active=True).count(),
        "total_trades": Trade.objects.count(),
        #"system_health": SystemHealth.get_status(),
    }
    return Response(data)
    '''