from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import APIException
from dotenv import load_dotenv
import os
import requests
from drf_spectacular.utils import OpenApiParameter, extend_schema, OpenApiTypes
from urllib.parse import urlencode

load_dotenv()

class CryptocurrencyQuotesLatestView(APIView):
    @extend_schema(
        operation_id="getCryptocurrencyQuotesLatest",
        description=(
            "Retrieve the latest market quote for one or more cryptocurrencies. "
            "Use this endpoint to request quotes for specific cryptocurrencies by ID, slug, or symbol. "
            "Supports optional conversions to fiat or other cryptocurrency values."
        ),
        parameters=[
            OpenApiParameter(
                "id",
                OpenApiTypes.STR,
                description="Comma-separated CoinMarketCap cryptocurrency IDs. Example: '1,2'.",
                required=False,
            ),
            OpenApiParameter(
                "slug",
                OpenApiTypes.STR,
                description="Comma-separated list of cryptocurrency slugs. Example: 'bitcoin,ethereum'.",
                required=False,
            ),
            OpenApiParameter(
                "symbol",
                OpenApiTypes.STR,
                description=(
                    "Comma-separated cryptocurrency symbols. Example: 'BTC,ETH'. "
                    "At least one of 'id', 'slug', or 'symbol' is required for this request."
                ),
                required=False,
            ),
            OpenApiParameter(
                "convert",
                OpenApiTypes.STR,
                description=(
                    "Optionally calculate market quotes in up to 120 currencies by passing a comma-separated list "
                    "of cryptocurrency or fiat currency symbols. Example: 'USD,BTC'."
                ),
                required=False,
            ),
            OpenApiParameter(
                "convert_id",
                OpenApiTypes.STR,
                description=(
                    "Optionally calculate market quotes by CoinMarketCap ID instead of symbol. "
                    "Example: '1,2781'. Cannot be used with 'convert'."
                ),
                required=False,
            ),
            OpenApiParameter(
                "aux",
                OpenApiTypes.STR,
                description=(
                    "Comma-separated list of supplemental fields to include. Supported values: "
                    "'num_market_pairs,cmc_rank,date_added,tags,platform,max_supply,circulating_supply,total_supply,"
                    "market_cap_by_total_supply,volume_24h_reported,volume_7d,volume_7d_reported,volume_30d,"
                    "volume_30d_reported,is_active,is_fiat'."
                ),
                required=False,
            ),
            OpenApiParameter(
                "skip_invalid",
                OpenApiTypes.BOOL,
                description=(
                    "Set to 'true' to skip invalid cryptocurrency lookups. "
                    "If not set or false, the API will return an error if any invalid cryptocurrencies are requested."
                ),
                required=False,
                default=False,
            ),
        ],
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 500: OpenApiTypes.OBJECT}
    )
    def get(self, request):
        api_url = os.getenv('COINMARKETCAP_URL', '')
        api_key = os.getenv('COINMARKETCAP_API_KEY', '')
        if not api_url or not api_key:
            raise APIException("Market data is temporarily unavailable")
        
        endpoint = '/v2/cryptocurrency/quotes/latest'

        # Extract and validate parameters
        params = {
            'id': request.GET.get('id'),
            'slug': request.GET.get('slug'),
            'symbol': request.GET.get('symbol'),
            'convert': request.GET.get('convert'),
            'convert_id': request.GET.get('convert_id'),
            'aux': request.GET.get('aux'),
            'skip_invalid': request.GET.get('skip_invalid', 'false'),
        }

        filtered_params = {k: v for k, v in params.items() if v is not None}

        url = f"{api_url}{endpoint}"
        headers = {
            "X-CMC_PRO_API_KEY": api_key,
        }

        try:
            response = requests.get(url, headers=headers, params=filtered_params)
            response.raise_for_status()  # Raise HTTPError for bad responses
            response_data = response.json()
        except requests.RequestException as e:
            raise APIException("Market data is temporarily unavailable") from e
        except ValueError as e:
            raise APIException("Market data is temporarily unavailable") from e
        
        if response.status_code == 200:
            return Response(response_data, status=status.HTTP_200_OK)
        raise APIException("Market data is temporarily unavailable")
