from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from dotenv import load_dotenv
import os
import requests
from rest_framework.decorators import api_view
from drf_spectacular.utils import OpenApiParameter, extend_schema, OpenApiTypes
from urllib.parse import urlencode

load_dotenv()

class CryptocurrencyMapView(APIView):
    @extend_schema(
        operation_id='getCryptocurrencyMap',
        description="Obtains a filtered list of cryptocurrencies from the market.",
        parameters=[
            OpenApiParameter('listing_status', OpenApiTypes.STR, description='Cryptocurrency listing status (e.g., "active")', required=False, default='active'),
            OpenApiParameter('start', OpenApiTypes.INT, description='Start index for the list (default is 1)', required=False, default=1),
            OpenApiParameter('limit', OpenApiTypes.INT, description='Maximum number of cryptocurrencies to return (default is 1000)', required=False, default=1000),
            OpenApiParameter('sort', OpenApiTypes.STR, description='Sort order of cryptocurrencies (default is "id")', required=False, default='id'),
            OpenApiParameter('symbol', OpenApiTypes.STR, description='Cryptocurrency symbol (e.g., "BTC")', required=False),
            OpenApiParameter('aux', OpenApiTypes.STR, description='Optional auxiliary parameter', required=False),
        ],
        responses={
            200: {
                'description': 'Successfully retrieved the cryptocurrency list.',
                'content': {'application/json': {'example': {}}}
            },
            400: {
                'description': 'Bad Request',
                'content': {'application/json': {'example': {"detail": "Invalid parameter value"}}}
            },
            500: {
                'description': 'Internal Server Error',
                'content': {'application/json': {'example': {"detail": "Server error"}}}
            }
        }
    )
    def get(self, request):
        # Load API configuration
        api_url = os.getenv('COINMARKETCAP_URL', '')
        api_key = os.getenv('COINMARKETCAP_API_KEY', '')
        if not api_url or not api_key:
            return Response({"detail": "API configuration is missing."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        endpoint = '/v1/cryptocurrency/map'

        # Extract and validate parameters
        listing_status = request.GET.get('listing_status', 'active')
        try:
            start = max(1, int(request.GET.get('start', 1)))  # Ensure start is at least 1
            limit = max(1, int(request.GET.get('limit', 1000)))  # Ensure limit is positive
        except ValueError:
            return Response({"detail": "Invalid type for 'start' or 'limit'."}, status=status.HTTP_400_BAD_REQUEST)

        sort = request.GET.get('sort', 'id')
        symbol = request.GET.get('symbol', '')
        aux = request.GET.get('aux', '')

        params = {
            'listing_status': listing_status,
            'start': start,
            'limit': limit,
            'sort': sort,
            'symbol': symbol,
            'aux': aux
        }

        filtered_params = {k: v for k, v in params.items() if v}

        url = f"{api_url}{endpoint}?{urlencode(filtered_params)}"
        headers = {
            'X-CMC_PRO_API_KEY': api_key
        }

        try:
            response = requests.get(url, headers=headers)
            response_data = response.json()
        except requests.RequestException as e:
            return Response({"detail": f"Error connecting to the API: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except ValueError:
            return Response({"detail": "Invalid response from the API."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if response.status_code == 200:
            return Response(response_data, status=status.HTTP_200_OK)
        else:
            return Response(response_data, status=response.status_code)
