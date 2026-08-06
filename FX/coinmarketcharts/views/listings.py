from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from dotenv import load_dotenv
import os
import requests
from coinmarketcharts.governance import authorize_coinmarketcap
from drf_spectacular.utils import OpenApiParameter, extend_schema, OpenApiTypes
from urllib.parse import urlencode

load_dotenv()

class CryptocurrencyListinglatestView(APIView):
    @extend_schema(
        operation_id="getCryptocurrencyListingLatest",
        description="Retrieve the latest cryptocurrency listings based on provided filters.",
        parameters=[
            OpenApiParameter('start', OpenApiTypes.INT, description='Starting point of the list (default 1)', required=False),
            OpenApiParameter('limit', OpenApiTypes.INT, description='Maximum number of results to return (default 99)', required=False),
            OpenApiParameter('price_min', OpenApiTypes.FLOAT, description='Minimum price filter', required=False),
            OpenApiParameter('price_max', OpenApiTypes.FLOAT, description='Maximum price filter', required=False),
            OpenApiParameter('market_cap_min', OpenApiTypes.FLOAT, description='Minimum market cap', required=False),
            OpenApiParameter('market_cap_max', OpenApiTypes.FLOAT, description='Maximum market cap', required=False),
            OpenApiParameter('volume_24h_min', OpenApiTypes.FLOAT, description='Minimum 24h volume', required=False),
            OpenApiParameter('volume_24h_max', OpenApiTypes.FLOAT, description='Maximum 24h volume', required=False),
            OpenApiParameter('circulating_supply_min', OpenApiTypes.FLOAT, description='Minimum circulating supply', required=False),
            OpenApiParameter('circulating_supply_max', OpenApiTypes.FLOAT, description='Maximum circulating supply', required=False),
            OpenApiParameter('percent_change_24h_min', OpenApiTypes.FLOAT, description='Minimum 24h percent change', required=False),
            OpenApiParameter('percent_change_24h_max', OpenApiTypes.FLOAT, description='Maximum 24h percent change', required=False),
            OpenApiParameter('convert', OpenApiTypes.STR, description='Currency for conversion (default USD)', required=False),
            OpenApiParameter('convert_id', OpenApiTypes.STR, description='Specific currency ID for conversion', required=False),
            OpenApiParameter('sort', OpenApiTypes.STR, description='Sort field (default market_cap)', required=False),
            OpenApiParameter('sort_dir', OpenApiTypes.STR, description='Sort direction (default desc)', required=False),
            OpenApiParameter('cryptocurrency_type', OpenApiTypes.STR, description='Type of cryptocurrency', required=False),
            OpenApiParameter('tag', OpenApiTypes.STR, description='Cryptocurrency tag filter', required=False),
            OpenApiParameter('aux', OpenApiTypes.STR, description='Additional fields to include', required=False),
        ]
    )
    def get(self, request):
        # Endpoint and API configuration
        endpoint = '/v1/cryptocurrency/listings/latest'
        api_url = os.getenv('COINMARKETCAP_URL', '')
        api_key = os.getenv('COINMARKETCAP_API_KEY', '')

        if not api_url or not api_key:
            return Response({"detail": "API configuration is missing."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        headers = {
            'Accepts': 'application/json',
            'X-CMC_PRO_API_KEY': api_key,
        }

        # Extract parameters from request
        query_params = {
            'start': request.GET.get('start', 1),
            'limit': request.GET.get('limit', 99),
            'price_min': request.GET.get('price_min'),
            'price_max': request.GET.get('price_max'),
            'market_cap_min': request.GET.get('market_cap_min'),
            'market_cap_max': request.GET.get('market_cap_max'),
            'volume_24h_min': request.GET.get('volume_24h_min'),
            'volume_24h_max': request.GET.get('volume_24h_max'),
            'circulating_supply_min': request.GET.get('circulating_supply_min'),
            'circulating_supply_max': request.GET.get('circulating_supply_max'),
            'percent_change_24h_min': request.GET.get('percent_change_24h_min'),
            'percent_change_24h_max': request.GET.get('percent_change_24h_max'),
            'convert': request.GET.get('convert', 'USD'),
            'convert_id': request.GET.get('convert_id'),
            'sort': request.GET.get('sort', 'market_cap'),
            'sort_dir': request.GET.get('sort_dir', 'desc'),
            'cryptocurrency_type': request.GET.get('cryptocurrency_type'),
            'tag': request.GET.get('tag'),
            'aux': request.GET.get('aux'),
        }

        # Remove None values
        filtered_params = {key: value for key, value in query_params.items() if value is not None}

        # Build the URL with parameters
        url = f"{api_url}{endpoint}?{urlencode(filtered_params)}"

        # Make the request to the external API
        try:
            authorize_coinmarketcap(product="LISTINGS")
            response = requests.get(url, headers=headers)
            response.raise_for_status()  # Raise HTTPError for bad responses (4xx and 5xx)
            return Response(response.json(), status=response.status_code)
        except requests.exceptions.RequestException as e:
            return Response({"detail": f"Error connecting to the API: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except ValueError:
            return Response({"detail": "Invalid response from the API."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CryptocurrencyListingHistoricalView(APIView):
    @extend_schema(
        operation_id="getCryptocurrencyListingHistorical",
        description=(
            "Retrieve a ranked and sorted list of all cryptocurrencies for a historical UTC date.\n\n"
            "This endpoint returns daily ranking snapshots from the end of each UTC day, starting from "
            "2013-04-28. Data can be sorted and paginated according to various parameters. Use the required "
            "`date` parameter to specify the snapshot date in Unix timestamp or ISO 8601 format (e.g., '2019-10-10')."
        ),
        parameters=[
            OpenApiParameter(
                "date",
                OpenApiTypes.STR,
                description="The date (Unix timestamp or ISO 8601) to reference the day of the snapshot (required).",
                required=True,
            ),
            OpenApiParameter(
                "start",
                OpenApiTypes.INT,
                description="Optionally offset the start (1-based index) of the paginated list of items to return. Default is 1.",
                required=False,
                default=1,
            ),
            OpenApiParameter(
                "limit",
                OpenApiTypes.INT,
                description="The number of results to return. Use with 'start' for pagination. Default is 100. Max is 5000.",
                required=False,
                default=100,
            ),
            OpenApiParameter(
                "convert",
                OpenApiTypes.STR,
                description=(
                    "Optionally calculate market quotes in up to 120 currencies by passing a comma-separated list "
                    "of cryptocurrency or fiat symbols (e.g., 'BTC,USD'). Each additional convert option requires an additional call credit."
                ),
                required=False,
            ),
            OpenApiParameter(
                "convert_id",
                OpenApiTypes.STR,
                description=(
                    "Optionally calculate market quotes by CoinMarketCap ID instead of symbols (e.g., '1,2781'). "
                    "Cannot be used with 'convert'."
                ),
                required=False,
            ),
            OpenApiParameter(
                "sort",
                OpenApiTypes.STR,
                description=(
                    "The field to sort the list of cryptocurrencies by. Default is 'cmc_rank'. Supported values include: "
                    "'cmc_rank', 'name', 'symbol', 'market_cap', 'price', 'circulating_supply', 'total_supply', 'max_supply', "
                    "'num_market_pairs', 'volume_24h', 'percent_change_1h', 'percent_change_24h', 'percent_change_7d'."
                ),
                required=False,
                default="cmc_rank",
            ),
            OpenApiParameter(
                "sort_dir",
                OpenApiTypes.STR,
                description="The direction in which to sort the list. Default is 'desc'. Supported values: 'asc', 'desc'.",
                required=False,
                default="desc",
            ),
            OpenApiParameter(
                "cryptocurrency_type",
                OpenApiTypes.STR,
                description=(
                    "The type of cryptocurrency to include. Default is 'all'. Supported values: 'all', 'coins', 'tokens'."
                ),
                required=False,
                default="all",
            ),
            OpenApiParameter(
                "aux",
                OpenApiTypes.STR,
                description=(
                    "Optionally specify a comma-separated list of supplemental data fields to return. Supported values include: "
                    "'platform', 'tags', 'date_added', 'circulating_supply', 'total_supply', 'max_supply', 'cmc_rank', "
                    "'num_market_pairs'. Pass 'platform,tags,date_added,circulating_supply,total_supply,max_supply,cmc_rank,num_market_pairs' to include all fields."
                ),
                required=False,
            ),
        ],
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 500: OpenApiTypes.OBJECT}
    )
    def get(self, request):
        api_url = os.getenv('COINMARKETCAP_URL', '')
        api_key = os.getenv('COINMARKETCAP_API_KEY', '')
        if not api_url or not api_key:
            return Response({"detail": "API configuration is missing."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        endpoint = '/v1/cryptocurrency/listings/historical'

        params = {
            'date': request.GET.get('date', ''),
            'start': request.GET.get('start', 1),
            'limit': request.GET.get('limit', 100),
            'convert': request.GET.get('convert', 'USD'),
            'convert_id': request.GET.get('convert_id', ''),
            'sort': request.GET.get('sort', 'market_cap'),
            'sort_dir': request.GET.get('sort_dir', 'desc'),
            'cryptocurrency_type': request.GET.get('cryptocurrency_type', ''),
            'aux': request.GET.get('aux', '')
        }

        filtered_params = {k: v for k, v in params.items() if v}

        url = f"{api_url}{endpoint}"
        headers = {
            'X-CMC_PRO_API_KEY': api_key
        }

        try:
            authorize_coinmarketcap(product="LISTINGS")
            response = requests.get(url, headers=headers, params=filtered_params)
            response.raise_for_status()
            response_data = response.json()
        except requests.RequestException as e:
            return Response({"detail": f"Error connecting to the API: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except ValueError:
            return Response({"detail": "Invalid response from the API."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(response_data, status=status.HTTP_200_OK)
