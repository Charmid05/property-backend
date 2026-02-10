from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import MaintenanceRequest


@admin.register(MaintenanceRequest)
class MaintenanceRequestAdmin(admin.ModelAdmin):
    """Admin interface for MaintenanceRequest model."""
    
    list_display = [
        'id',
        'title',
        'tenant',
        'unit',
        'property',
        'category',
        'priority',
        'status',
        'reported_date',
        'assigned_to',
    ]
    
    list_filter = [
        'status',
        'priority',
        'category',
        'reported_date',
        'scheduled_date',
        'completed_date',
    ]
    
    search_fields = [
        'title',
        'description',
        'tenant__first_name',
        'tenant__last_name',
        'tenant__email',
        'unit__unit_number',
        'property__name',
    ]
    
    readonly_fields = [
        'reported_date',
        'created_at',
        'updated_at',
    ]
    
    fieldsets = (
        (_('Request Information'), {
            'fields': (
                'tenant',
                'unit',
                'property',
                'title',
                'description',
            )
        }),
        (_('Classification'), {
            'fields': (
                'category',
                'priority',
                'status',
            )
        }),
        (_('Assignment & Scheduling'), {
            'fields': (
                'assigned_to',
                'scheduled_date',
                'completed_date',
            )
        }),
        (_('Cost Information'), {
            'fields': (
                'estimated_cost',
                'actual_cost',
            )
        }),
        (_('Notes'), {
            'fields': (
                'tenant_notes',
                'notes',
            )
        }),
        (_('Timestamps'), {
            'fields': (
                'reported_date',
                'created_at',
                'updated_at',
            ),
            'classes': ('collapse',)
        }),
    )
    
    date_hierarchy = 'reported_date'
    
    list_per_page = 25
    
    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        queryset = super().get_queryset(request)
        return queryset.select_related(
            'tenant',
            'unit',
            'property',
            'assigned_to'
        )

