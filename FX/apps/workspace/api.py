from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from rest_framework import exceptions, permissions, status, views
from rest_framework.response import Response

from integrations.models import OrganizationMembership
from integrations.permissions import organization_for_request

from .commands import (
    begin_command,
    complete_response,
    error_body,
    parse_command,
    version_error,
)
from .instruments import (
    InstrumentResolutionError,
    normalize_removal_reference,
    resolve_active_instrument,
)
from .models import Watchlist, WatchlistItem
from .serializers import WatchlistItemSerializer, WatchlistSerializer


class WorkspaceOwnedView(views.APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def organization(self):
        if not hasattr(self, "_workspace_organization"):
            try:
                self._workspace_organization = organization_for_request(self.request)
            except ObjectDoesNotExist as exc:
                raise exceptions.PermissionDenied(
                    "organization context is not available"
                ) from exc
        return self._workspace_organization

    def watchlists(self):
        return Watchlist.objects.filter(
            organization=self.organization(),
            user=self.request.user,
        ).prefetch_related("items")

    def watchlist(self, watchlist_id, *, lock=False):
        rows = Watchlist.objects.filter(
            organization=self.organization(),
            user=self.request.user,
            pk=watchlist_id,
        )
        if lock:
            rows = rows.select_for_update()
        return rows.prefetch_related("items").first()

    def lock_membership(self):
        return OrganizationMembership.objects.select_for_update().get(
            user=self.request.user,
            organization=self.organization(),
        )


class WatchlistCollectionView(WorkspaceOwnedView):
    def get(self, request):
        rows = self.watchlists()
        return Response({"results": WatchlistSerializer(rows, many=True).data})

    def post(self, request):
        serializer = WatchlistSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = self.organization()
        command, response = parse_command(request, require_version=False)
        if response:
            return response
        record, response = begin_command(
            request,
            organization=organization,
            command=command,
            operation="watchlist.create",
            resource_ref="collection",
            payload={"name": serializer.validated_data["name"]},
        )
        if response:
            return response

        with transaction.atomic():
            self.lock_membership()
            is_default = not Watchlist.objects.filter(
                organization=organization,
                user=request.user,
            ).exists()
            try:
                with transaction.atomic():
                    row = Watchlist.objects.create(
                        organization=organization,
                        user=request.user,
                        name=serializer.validated_data["name"],
                        is_default=is_default,
                    )
            except IntegrityError:
                body = error_body("WATCHLIST_ALREADY_EXISTS")
                complete_response(
                    record,
                    request=request,
                    organization=organization,
                    command=command,
                    status_code=409,
                    body=body,
                    resource_type="workspace_watchlist",
                    resource_id="collection",
                )
                return Response(body, status=409)

            data = WatchlistSerializer(row).data
            complete_response(
                record,
                request=request,
                organization=organization,
                command=command,
                status_code=201,
                body=data,
                resource_type="workspace_watchlist",
                resource_id=row.pk,
                action="workspace.watchlist.created",
                after=data,
            )
        return Response(data, status=status.HTTP_201_CREATED)


class WatchlistDetailView(WorkspaceOwnedView):
    def get(self, request, watchlist_id):
        row = self.watchlist(watchlist_id)
        if row is None:
            return Response(error_body("RESOURCE_NOT_FOUND"), status=404)
        return Response(WatchlistSerializer(row).data)

    def patch(self, request, watchlist_id):
        input_serializer = WatchlistSerializer(data=request.data, partial=True)
        input_serializer.is_valid(raise_exception=True)
        if "name" not in input_serializer.validated_data:
            return Response(error_body("WATCHLIST_NAME_REQUIRED"), status=400)

        organization = self.organization()
        command, response = parse_command(request, require_version=True)
        if response:
            return response
        record, response = begin_command(
            request,
            organization=organization,
            command=command,
            operation="watchlist.rename",
            resource_ref=str(watchlist_id),
            payload={"name": input_serializer.validated_data["name"]},
        )
        if response:
            return response

        with transaction.atomic():
            self.lock_membership()
            row = self.watchlist(watchlist_id, lock=True)
            if row is None:
                body = error_body("RESOURCE_NOT_FOUND")
                complete_response(
                    record,
                    request=request,
                    organization=organization,
                    command=command,
                    status_code=404,
                    body=body,
                    resource_type="workspace_watchlist",
                    resource_id=watchlist_id,
                )
                return Response(body, status=404)
            if row.version != command.expected_version:
                response = version_error(row.version)
                complete_response(
                    record,
                    request=request,
                    organization=organization,
                    command=command,
                    status_code=response.status_code,
                    body=response.data,
                    resource_type="workspace_watchlist",
                    resource_id=row.pk,
                )
                return response

            before = WatchlistSerializer(row).data
            row.name = input_serializer.validated_data["name"]
            row.version += 1
            try:
                with transaction.atomic():
                    row.save(update_fields=("name", "version", "updated_at"))
            except IntegrityError:
                body = error_body("WATCHLIST_ALREADY_EXISTS")
                complete_response(
                    record,
                    request=request,
                    organization=organization,
                    command=command,
                    status_code=409,
                    body=body,
                    resource_type="workspace_watchlist",
                    resource_id=row.pk,
                )
                return Response(body, status=409)

            data = WatchlistSerializer(row).data
            complete_response(
                record,
                request=request,
                organization=organization,
                command=command,
                status_code=200,
                body=data,
                resource_type="workspace_watchlist",
                resource_id=row.pk,
                action="workspace.watchlist.renamed",
                before=before,
                after=data,
            )
        return Response(data)

    def delete(self, request, watchlist_id):
        organization = self.organization()
        command, response = parse_command(request, require_version=True)
        if response:
            return response
        record, response = begin_command(
            request,
            organization=organization,
            command=command,
            operation="watchlist.delete",
            resource_ref=str(watchlist_id),
            payload={},
        )
        if response:
            return response

        with transaction.atomic():
            self.lock_membership()
            row = self.watchlist(watchlist_id, lock=True)
            if row is None:
                body = error_body("RESOURCE_NOT_FOUND")
                complete_response(
                    record,
                    request=request,
                    organization=organization,
                    command=command,
                    status_code=404,
                    body=body,
                    resource_type="workspace_watchlist",
                    resource_id=watchlist_id,
                )
                return Response(body, status=404)
            if row.version != command.expected_version:
                response = version_error(row.version)
                complete_response(
                    record,
                    request=request,
                    organization=organization,
                    command=command,
                    status_code=response.status_code,
                    body=response.data,
                    resource_type="workspace_watchlist",
                    resource_id=row.pk,
                )
                return response

            before = WatchlistSerializer(row).data
            was_default = row.is_default
            row_id = row.pk
            row.delete()
            if was_default:
                replacement = (
                    Watchlist.objects.select_for_update()
                    .filter(organization=organization, user=request.user)
                    .order_by("created_at", "id")
                    .first()
                )
                if replacement is not None:
                    replacement.is_default = True
                    replacement.version += 1
                    replacement.save(
                        update_fields=("is_default", "version", "updated_at")
                    )

            complete_response(
                record,
                request=request,
                organization=organization,
                command=command,
                status_code=204,
                body=None,
                resource_type="workspace_watchlist",
                resource_id=row_id,
                action="workspace.watchlist.deleted",
                before=before,
                after={"deleted": True},
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class WatchlistItemCollectionView(WorkspaceOwnedView):
    def get(self, request, watchlist_id):
        row = self.watchlist(watchlist_id)
        if row is None:
            return Response(error_body("RESOURCE_NOT_FOUND"), status=404)
        return Response(
            {
                "watchlist_version": row.version,
                "results": WatchlistItemSerializer(row.items.all(), many=True).data,
            }
        )

    def post(self, request, watchlist_id):
        try:
            instrument = resolve_active_instrument(request.data.get("instrument_id"))
        except InstrumentResolutionError as exc:
            status_code = {
                "INSTRUMENT_REQUIRED": 400,
                "INSTRUMENT_UNAVAILABLE": 404,
                "INSTRUMENT_AMBIGUOUS": 409,
            }.get(exc.code, 400)
            return Response(error_body(exc.code), status=status_code)

        item_serializer = WatchlistItemSerializer(
            data={
                "instrument_id": str(instrument.instrument_id),
                "sort_order": request.data.get("sort_order", 0),
            },
            context={"resolved_instrument": instrument},
        )
        item_serializer.is_valid(raise_exception=True)

        organization = self.organization()
        command, response = parse_command(request, require_version=True)
        if response:
            return response
        record, response = begin_command(
            request,
            organization=organization,
            command=command,
            operation="watchlist_item.add",
            resource_ref=str(watchlist_id),
            payload={
                "instrument_id": str(instrument.instrument_id),
                "sort_order": item_serializer.validated_data.get("sort_order", 0),
            },
        )
        if response:
            return response

        with transaction.atomic():
            self.lock_membership()
            row = self.watchlist(watchlist_id, lock=True)
            if row is None:
                body = error_body("RESOURCE_NOT_FOUND")
                complete_response(
                    record,
                    request=request,
                    organization=organization,
                    command=command,
                    status_code=404,
                    body=body,
                    resource_type="workspace_watchlist",
                    resource_id=watchlist_id,
                )
                return Response(body, status=404)
            if row.version != command.expected_version:
                response = version_error(row.version)
                complete_response(
                    record,
                    request=request,
                    organization=organization,
                    command=command,
                    status_code=response.status_code,
                    body=response.data,
                    resource_type="workspace_watchlist",
                    resource_id=row.pk,
                )
                return response

            existing = WatchlistItem.objects.filter(
                watchlist=row,
                instrument_id=str(instrument.instrument_id),
            ).first()
            if existing is not None:
                data = {
                    **WatchlistItemSerializer(existing).data,
                    "watchlist_version": row.version,
                }
                complete_response(
                    record,
                    request=request,
                    organization=organization,
                    command=command,
                    status_code=200,
                    body=data,
                    resource_type="workspace_watchlist_item",
                    resource_id=existing.pk,
                )
                return Response(data)

            before = {"version": row.version}
            item = WatchlistItem.objects.create(
                watchlist=row,
                instrument_id=item_serializer.validated_data["instrument_id"],
                sort_order=item_serializer.validated_data.get("sort_order", 0),
            )
            row.version += 1
            row.save(update_fields=("version", "updated_at"))
            data = {
                **WatchlistItemSerializer(item).data,
                "watchlist_version": row.version,
            }
            complete_response(
                record,
                request=request,
                organization=organization,
                command=command,
                status_code=201,
                body=data,
                resource_type="workspace_watchlist_item",
                resource_id=item.pk,
                action="workspace.watchlist_item.added",
                before=before,
                after=data,
            )
        return Response(data, status=status.HTTP_201_CREATED)


class WatchlistItemDetailView(WorkspaceOwnedView):
    def delete(self, request, watchlist_id, instrument_id):
        try:
            reference = normalize_removal_reference(instrument_id)
        except InstrumentResolutionError as exc:
            status_code = 409 if exc.code == "INSTRUMENT_AMBIGUOUS" else 404
            return Response(error_body(exc.code), status=status_code)

        organization = self.organization()
        command, response = parse_command(request, require_version=True)
        if response:
            return response
        record, response = begin_command(
            request,
            organization=organization,
            command=command,
            operation="watchlist_item.delete",
            resource_ref=f"{watchlist_id}:{reference}",
            payload={"instrument_id": reference},
        )
        if response:
            return response

        with transaction.atomic():
            self.lock_membership()
            row = self.watchlist(watchlist_id, lock=True)
            if row is None:
                body = error_body("RESOURCE_NOT_FOUND")
                complete_response(
                    record,
                    request=request,
                    organization=organization,
                    command=command,
                    status_code=404,
                    body=body,
                    resource_type="workspace_watchlist",
                    resource_id=watchlist_id,
                )
                return Response(body, status=404)
            if row.version != command.expected_version:
                response = version_error(row.version)
                complete_response(
                    record,
                    request=request,
                    organization=organization,
                    command=command,
                    status_code=response.status_code,
                    body=response.data,
                    resource_type="workspace_watchlist",
                    resource_id=row.pk,
                )
                return response

            item = WatchlistItem.objects.select_for_update().filter(
                watchlist=row,
                instrument_id=reference,
            ).first()
            if item is None:
                body = error_body("RESOURCE_NOT_FOUND")
                complete_response(
                    record,
                    request=request,
                    organization=organization,
                    command=command,
                    status_code=404,
                    body=body,
                    resource_type="workspace_watchlist_item",
                    resource_id=reference,
                )
                return Response(body, status=404)

            before = WatchlistItemSerializer(item).data
            item_id = item.pk
            item.delete()
            row.version += 1
            row.save(update_fields=("version", "updated_at"))
            complete_response(
                record,
                request=request,
                organization=organization,
                command=command,
                status_code=204,
                body=None,
                resource_type="workspace_watchlist_item",
                resource_id=item_id,
                action="workspace.watchlist_item.deleted",
                before=before,
                after={"deleted": True, "watchlist_version": row.version},
            )
        return Response(status=status.HTTP_204_NO_CONTENT)
