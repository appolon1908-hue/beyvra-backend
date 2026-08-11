from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from dotenv import load_dotenv
import os
import requests
from coinmarketcharts.governance import authorize_coinmarketcap
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
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 500: OpenApiTypes.OBJECT}
    )
    def get(self, request):
        # Load API configuration
        api_url = os.getenv('COINMARKETCAP_URL', '')
        api_key = os.getenv('COINMARKETCAP_API_KEY', '')
        if not api_url or not api_key:
            raise APIException("Market data is temporarily unavailable")

        endpoint = '/v1/cryptocurrency/map'

        # Extract and validate parameters
        listing_status = request.GET.get('listing_status', 'active')
        try:
            start = max(1, int(request.GET.get('start', 1)))  # Ensure start is at least 1
            limit = max(1, int(request.GET.get('limit', 1000)))  # Ensure limit is positive
        except ValueError:
            raise ValidationError("Invalid pagination parameters")

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
            authorize_coinmarketcap(product="ASSET_MAP")
            response = requests.get(url, headers=headers)
            response_data = response.json()
        except requests.RequestException as e:
            raise APIException("Market data is temporarily unavailable") from e
        except ValueError as e:
            raise APIException("Market data is temporarily unavailable") from e

        if response.status_code == 200:
            return Response(response_data, status=status.HTTP_200_OK)
        raise APIException("Market data is temporarily unavailable")
