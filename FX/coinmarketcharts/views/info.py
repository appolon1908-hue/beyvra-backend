from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from dotenv import load_dotenv
import os
import requests
from drf_spectacular.utils import OpenApiParameter, extend_schema, OpenApiTypes

load_dotenv()

class CryptocurrencyInfoView(APIView):
    @extend_schema(
    operation_id="getCryptocurrencyInfo",
    description="Retrieve detailed information about one or more cryptocurrencies using various filtering options.",
    parameters=[
        OpenApiParameter(
            "id",
            OpenApiTypes.STR,
            description=(
                "One or more comma-separated CoinMarketCap cryptocurrency IDs. "
                "Example: '1,2'."
            ),
            required=False,
        ),
        OpenApiParameter(
            "slug",
            OpenApiTypes.STR,
            description=(
                "Alternatively, pass a comma-separated list of cryptocurrency slugs. "
                "Example: 'bitcoin,ethereum'."
            ),
            required=False,
        ),
        OpenApiParameter(
            "symbol",
            OpenApiTypes.STR,
            description=(
                "Alternatively, pass one or more comma-separated cryptocurrency symbols. "
                "Example: 'BTC,ETH'. At least one of 'id', 'slug', or 'symbol' is required. "
                "For non-unique symbols, results will include all matches as an array."
            ),
            required=False,
        ),
        OpenApiParameter(
            "address",
            OpenApiTypes.STR,
            description=(
                "Alternatively, pass in a contract address. "
                "Example: '0xc40af1e4fecfa05ce6bab79dcd8b373d2e436c4e'."
            ),
            required=False,
        ),
        OpenApiParameter(
            "skip_invalid",
            OpenApiTypes.BOOL,
            description=(
                "Pass 'true' to relax request validation rules. When requesting multiple cryptocurrencies, "
                "an error is returned if any invalid cryptocurrencies are requested or if there is no matching record. "
                "Setting this to 'true' skips invalid lookups, returning valid results."
            ),
            required=False,
            default=False,
        ),
        OpenApiParameter(
            "aux",
            OpenApiTypes.STR,
            description=(
                "Optionally specify a comma-separated list of supplemental data fields to return. "
                "Valid values include 'urls,logo,description,tags,platform,date_added,notice,status'. "
                "To include all fields, pass 'urls,logo,description,tags,platform,date_added,notice,status'."
            ),
            required=False,
        ),
    ],
    responses={
        200: {
            'description': 'Successfully retrieved cryptocurrency information.',
            'content': {'application/json': {'example': {}}}
        },
        400: {
            'description': 'Bad request. Invalid parameters or missing required values.',
            'content': {'application/json': {'example': {"error": "Invalid request. At least one of 'id', 'slug', or 'symbol' is required."}}}
        },
        500: {
            'description': 'Internal server error.',
            'content': {'application/json': {'example': {"error": "An unexpected error occurred while processing the request."}}}
        }
    }
)
    def get(self, request):
        # Endpoint and base API URL
        endpoint = '/v2/cryptocurrency/info'
        api_url = os.getenv('COINMARKETCAP_URL', '') + endpoint
        api_key = os.getenv("COINMARKETCAP_API_KEY", '')

        if not api_key or not api_url:
            return Response({"error": "API configuration is missing."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Headers
        headers = {
            "Accepts": "application/json",
            "X-CMC_PRO_API_KEY": api_key,
        }

        # Retrieve and validate query parameters
        query_params = {
            "id": request.GET.get("id"),
            "slug": request.GET.get("slug"),
            "symbol": request.GET.get("symbol"),
            "address": request.GET.get("address"),
            "skip_invalid": request.GET.get("skip_invalid", "false"),
            "aux": request.GET.get("aux"),
        }

        # Ensure at least one required parameter is provided
        if not any(query_params[key] for key in ["id", "slug", "symbol", "address"]):
            return Response(
                {"error": "Invalid request. At least one of 'id', 'slug', 'symbol', or 'address' is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Remove None values from query parameters
        filtered_params = {k: v for k, v in query_params.items() if v is not None}

        try:
            # Make the API request
            response = requests.get(api_url, headers=headers, params=filtered_params)
            response_data = response.json()

            if response.status_code == 200:
                return Response(response_data, status=status.HTTP_200_OK)
            else:
                return Response(response_data, status=response.status_code)
        except requests.RequestException as e:
            return Response({"error": f"Error connecting to the API: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except ValueError:
            return Response({"error": "Invalid response from the API."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
