from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
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
        responses={
            200: {
                "description": "Successfully retrieved the latest cryptocurrency quotes.",
                "content": {
                    "application/json": {
                        "example": {
                            "status": {
                                "timestamp": "2024-11-27T12:00:00.000Z",
                                "error_code": 0,
                                "error_message": None,
                                "elapsed": 10,
                                "credit_count": 1
                            },
                            "data": {
                                "BTC": {
                                    "id": 1,
                                    "name": "Bitcoin",
                                    "symbol": "BTC",
                                    "quote": {
                                        "USD": {
                                            "price": 54300.45,
                                            "volume_24h": 35673820000,
                                            "market_cap": 1065312000000,
                                            "percent_change_1h": 0.12,
                                            "percent_change_24h": 1.56,
                                            "percent_change_7d": -2.34,
                                            "last_updated": "2024-11-27T12:00:00.000Z"
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            400: {
                "description": "Bad Request. Invalid parameter value or missing required parameters.",
                "content": {
                    "application/json": {"example": {"detail": "Invalid request parameters."}}
                }
            },
            500: {
                "description": "Internal Server Error.",
                "content": {
                    "application/json": {"example": {"detail": "An unexpected error occurred while processing the request."}}
                }
            },
        }
    )
    def get(self, request):
        api_url = os.getenv('COINMARKETCAP_URL', '')
        api_key = os.getenv('COINMARKETCAP_API_KEY', '')
        if not api_url or not api_key:
            return Response({"detail": "API configuration is missing."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
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
            return Response({"detail": f"Error connecting to the API: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except ValueError:
            return Response({"detail": "Invalid response from the API."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        if response.status_code == 200:
            return Response(response_data, status=status.HTTP_200_OK)
        else:
            return Response(response_data, status=response.status_code)




