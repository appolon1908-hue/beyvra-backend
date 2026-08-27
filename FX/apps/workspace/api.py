from django.db import IntegrityError, transaction
from rest_framework import permissions, status, views
from rest_framework.response import Response

from apps.trading.api.errors import error_response
from integrations.permissions import organization_for_request
from .instruments import InstrumentResolutionError, resolve_active_instrument
from .models import Watchlist, WatchlistItem
from .serializers import WatchlistItemSerializer, WatchlistSerializer


class WorkspaceOwnedView(views.APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def organization(self):
        return organization_for_request(self.request)

    def watchlists(self):
        return Watchlist.objects.filter(
            organization=self.organization(),
            user=self.request.user,
        ).prefetch_related("items")

    def watchlist(self, watchlist_id):
        return self.watchlists().filter(pk=watchlist_id).first()


class WatchlistCollectionView(WorkspaceOwnedView):
    def get(self, request):
        rows = self.watchlists()
        return Response({"results": WatchlistSerializer(rows, many=True).data})

    @transaction.atomic
    def post(self, request):
        serializer = WatchlistSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        has_watchlist = self.watchlists().exists()
        try:
            row = Watchlist.objects.create(
                organization=self.organization(),
                user=request.user,
                name=serializer.validated_data["name"],
                is_default=not has_watchlist,
            )
        except IntegrityError:
            return error_response(request, "WATCHLIST_ALREADY_EXISTS", 409)
        return Response(WatchlistSerializer(row).data, status=status.HTTP_201_CREATED)


class WatchlistDetailView(WorkspaceOwnedView):
    def get(self, request, watchlist_id):
        row = self.watchlist(watchlist_id)
        if row is None:
            return error_response(request, "RESOURCE_NOT_FOUND", 404)
        return Response(WatchlistSerializer(row).data)

    @transaction.atomic
    def patch(self, request, watchlist_id):
        row = self.watchlist(watchlist_id)
        if row is None:
            return error_response(request, "RESOURCE_NOT_FOUND", 404)
        serializer = WatchlistSerializer(row, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            serializer.save()
        except IntegrityError:
            return error_response(request, "WATCHLIST_ALREADY_EXISTS", 409)
        return Response(serializer.data)

    @transaction.atomic
    def delete(self, request, watchlist_id):
        row = self.watchlist(watchlist_id)
        if row is None:
            return error_response(request, "RESOURCE_NOT_FOUND", 404)
        was_default = row.is_default
        row.delete()
        if was_default:
            replacement = self.watchlists().order_by("created_at", "id").first()
            if replacement is not None:
                replacement.is_default = True
                replacement.save(update_fields=("is_default", "updated_at"))
        return Response(status=status.HTTP_204_NO_CONTENT)


class WatchlistItemCollectionView(WorkspaceOwnedView):
    def get(self, request, watchlist_id):
        row = self.watchlist(watchlist_id)
        if row is None:
            return error_response(request, "RESOURCE_NOT_FOUND", 404)
        return Response({"results": WatchlistItemSerializer(row.items.all(), many=True).data})

    def post(self, request, watchlist_id):
        row = self.watchlist(watchlist_id)
        if row is None:
            return error_response(request, "RESOURCE_NOT_FOUND", 404)
        try:
            instrument = resolve_active_instrument(request.data.get("instrument_id"))
        except InstrumentResolutionError as exc:
            status_code = {
                "INSTRUMENT_REQUIRED": 400,
                "INSTRUMENT_UNAVAILABLE": 404,
                "INSTRUMENT_AMBIGUOUS": 409,
            }.get(exc.code, 400)
            return error_response(request, exc.code, status_code)
        serializer = WatchlistItemSerializer(
            data=request.data,
            context={"resolved_instrument": instrument},
        )
        serializer.is_valid(raise_exception=True)
        item, created = WatchlistItem.objects.get_or_create(
            watchlist=row,
            instrument_id=serializer.validated_data["instrument_id"],
            defaults={"sort_order": serializer.validated_data.get("sort_order", 0)},
        )
        return Response(
            WatchlistItemSerializer(item).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class WatchlistItemDetailView(WorkspaceOwnedView):
    def delete(self, request, watchlist_id, instrument_id):
        row = self.watchlist(watchlist_id)
        if row is None:
            return error_response(request, "RESOURCE_NOT_FOUND", 404)
        try:
            reference = str(resolve_active_instrument(instrument_id).instrument_id)
        except InstrumentResolutionError as exc:
            status_code = 409 if exc.code == "INSTRUMENT_AMBIGUOUS" else 404
            return error_response(request, exc.code, status_code)
        deleted, _ = WatchlistItem.objects.filter(
            watchlist=row,
            instrument_id=reference,
        ).delete()
        if not deleted:
            return error_response(request, "RESOURCE_NOT_FOUND", 404)
        return Response(status=status.HTTP_204_NO_CONTENT)
