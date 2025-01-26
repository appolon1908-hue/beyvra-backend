from django.core.exceptions import ValidationError
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from tickets.models import SupportTicket, TicketMessages
from tickets.serializers import TicketSerializer


class GetTicketView(APIView):
    """Get a support ticket from the system."""

    permission_classes = [permissions.AllowAny]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="id",
                description="The UUID of the support ticket",
                required=True,
                type=str,
            )
        ],
        responses={200: TicketSerializer},
    )
    def get(self, request):
        ticket_id = request.query_params.get("id")  # Retrieve the 'id' from query parameters
        if not ticket_id:
            return Response({"detail": "ID query parameter is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            ticket = SupportTicket.objects.get(id=ticket_id)
        except SupportTicket.DoesNotExist:
            return Response({"detail": TicketMessages.TICKET_NOT_FOUND.value}, status=status.HTTP_404_NOT_FOUND)
        except ValidationError as e:
            return Response({"detail": e}, status=status.HTTP_400_BAD_REQUEST)
        ticket_data = TicketSerializer(ticket).data
        return Response(ticket_data, status=status.HTTP_200_OK)
