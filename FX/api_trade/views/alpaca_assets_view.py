from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework.decorators import api_view
from rest_framework.response import Response

from ..scripts.alpaca_integration import AlpacaIntegrationAssets


@extend_schema(
    parameters=[
        OpenApiParameter(
            name="status",
            required=False,
            type=OpenApiTypes.STR,
            default="active",
            enum=["active", "inactive"],
        ),
        OpenApiParameter(
            name="asset_class",
            required=True,
            type=OpenApiTypes.STR,
            default="crypto",
            enum=["us_equity", "us_option", "crypto"],
        ),
        OpenApiParameter(
            name="exchange",
            required=False,
            type=OpenApiTypes.STR,
            default="CRYPTO",
            enum=[
                "AMEX",
                "ARCA",
                "BATS",
                "NYSE",
                "NASDAQ",
                "NYSEARCA",
                "FTXU",
                "CBSE",
                "GNSS",
                "ERSX",
                "OTC",
                "CRYPTO",
            ],
        ),
        OpenApiParameter(
            name="page_size",
            required=False,
            type=OpenApiTypes.INT,
            default=10,
        ),
        OpenApiParameter(
            name="page",
            required=False,
            type=OpenApiTypes.INT,
            default=1,
        ),
    ]
)
@api_view(["GET"])
def get_assets(request):
    """
    When querying for available assets, this model provides the parameters that can be filtered by.

    - Attributes:
       * status (Optional[AssetStatus]): The active status of the asset.
        * asset_class (Optional[AssetClass]): The type of asset (i.e. us_equity, crypto).
        * exchange (Optional[AssetExchange]): The exchange the asset trades on.

    """
    result = AlpacaIntegrationAssets().get_assets(request=request)

    return Response(result)


@extend_schema(
    parameters=[
        OpenApiParameter(
            name="asset",
            required=True,
            type=OpenApiTypes.STR,
            default="AAPL",
        ),
    ],
)
@api_view(["GET"])
def get_asset(request):
    """
    Returns a specific asset by its symbol or asset id. If the specified asset does not exist
    a 404 error will be thrown.

    - Args:
        * symbol_or_asset_id (Union[UUID, str]): The symbol or asset id for the specified asset

    - Returns:
        * Asset: The asset if it exists.
    """
    result, error_message = AlpacaIntegrationAssets().get_asset(request=request)
    if result is None:
        return Response({"error": error_message}, status=404)
    return Response(result)
