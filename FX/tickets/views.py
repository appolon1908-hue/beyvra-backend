from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import permissions, status
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from tickets.models import SupportTicket, TicketMessages
from tickets.serializers import GetTicketSerializer, TicketSerializer


class GetTicketView(APIView):
    """Get a support ticket from the system."""

    permission_classes = [permissions.IsAdminUser]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="id",
                description="The UUID of the support ticket",
                required=False,
                type=str,
            )
        ],
        responses={200: TicketSerializer},
    )
    def get(self, request):
        query_params = {"id": request.query_params.get("id")}

        # Validate query parameters with serializer
        serializer = GetTicketSerializer(data=query_params)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        ticket_id = serializer.validated_data.get("id")

        # If 'id' is provided, fetch the specific ticket
        if ticket_id:
            try:
                ticket = SupportTicket.objects.get(id=ticket_id)
            except SupportTicket.DoesNotExist:
                return Response({"detail": TicketMessages.TICKET_NOT_FOUND.value}, status=status.HTTP_404_NOT_FOUND)

            ticket_data = TicketSerializer(ticket).data
            return Response(ticket_data, status=status.HTTP_200_OK)

        # If 'id' is not provided, paginate all tickets
        tickets = SupportTicket.objects.all()
        paginator = LimitOffsetPagination()
        paginated_tickets = paginator.paginate_queryset(tickets, request)
        ticket_data = TicketSerializer(paginated_tickets, many=True).data

        return paginator.get_paginated_response(ticket_data)
