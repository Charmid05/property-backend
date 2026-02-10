from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q

from .models import Office
from .serializers import OfficeSerializer


class OfficeViewSet(viewsets.ModelViewSet):
    queryset = Office.objects.all()
    serializer_class = OfficeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Office.objects.all()
        # If user is a property manager, show only their offices
        if self.request.user.role == 'property_manager':
            queryset = queryset.filter(manager=self.request.user)

        return queryset

    @action(detail=False, methods=['get'])
    def my_offices(self, request):
        offices = Office.objects.filter(manager=request.user)
        serializer = self.get_serializer(offices, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def properties(self, request, pk=None):
        """
        Get all properties associated with this office
        """
        office = self.get_object()
        properties = office.properties.all()
        serializer = PropertySerializer(properties, many=True)
        return Response(serializer.data)
        return Response({
            "message": "This endpoint will return properties associated with this office",
            "office_id": office.id,
            "office_name": office.name
        })

    @action(detail=False, methods=['get'])
    def search_by_location(self, request):
        location = request.query_params.get('location', '')
        if not location:
            return Response(
                {"error": "Location parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        offices = Office.objects.filter(
            Q(address__icontains=location) |
            Q(name__icontains=location)
        )
        serializer = self.get_serializer(offices, many=True)
        return Response(serializer.data)

    def perform_create(self, serializer):
        if not serializer.validated_data.get('manager'):
            if self.request.user.role in ['property_manager', 'admin', 'landlord']:
                serializer.save(manager=self.request.user)
            else:
                serializer.save()
        else:
            serializer.save()

    def destroy(self, request, *args, **kwargs):
        office = self.get_object()

        # Check if office has associated properties (if applicable)
        if office.properties.exists():
            return Response(
                {"error": "Cannot delete office with associated properties"},
                status=status.HTTP_400_BAD_REQUEST
            )

        return super().destroy(request, *args, **kwargs)
