from property.models import Property
from a_users.models import CustomUser
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from .models import Office, Unit

class PropertyManagerSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['id', 'first_name', 'last_name', 'email', 'role']
        read_only_fields = ['id', 'role']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['full_name'] = f"{instance.first_name} {instance.last_name}".strip(
        )
        return data
class PropertyListSerializer(serializers.ModelSerializer):
    manager_name = serializers.SerializerMethodField()
    vacancy_rate = serializers.SerializerMethodField()
    total_units = serializers.IntegerField(read_only=True)
    occupied_units_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Property
        fields = [
            'id',
            'name',
            'address',
            'manager_name',
            'is_active',
            'total_units',
            'occupied_units_count',
            'vacancy_rate',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'total_units',
            'occupied_units_count',
            'vacancy_rate',
            'created_at',
            'updated_at',
        ]

    def get_manager_name(self, obj):
        if obj.manager:
            return f"{obj.manager.first_name} {obj.manager.last_name}".strip()
        return None

    def get_vacancy_rate(self, obj):
        if not obj.total_units or obj.total_units == 0:
            return 0
        vacant = obj.total_units - obj.occupied_units_count
        return round((vacant / obj.total_units) * 100, 2)



class PropertyDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for property with full information"""
    manager = PropertyManagerSerializer(read_only=True)
    vacancy_rate = serializers.ReadOnlyField()
    picture_url = serializers.SerializerMethodField()

    class Meta:
        model = Property
        fields = [
            'id', 'name', 'address', 'description',  'manager',
            'picture', 'picture_url', 'is_active', 'vacancy_rate',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'vacancy_rate', 'created_at', 'updated_at'
        ]
    def get_picture_url(self, obj):
        if obj.picture:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.picture.url)
            return obj.picture.url
        return None

class PropertyCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating properties"""
    picture = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = Property
        fields = [
            'name', 'address', 'description',
            'picture', 'is_active'
        ]

    def validate_name(self, value):
        """Validate property name uniqueness"""
        instance = getattr(self, 'instance', None)
        if Property.objects.filter(name=value).exclude(
            pk=instance.pk if instance else None
        ).exists():
            raise serializers.ValidationError(
                _("A property with this name already exists.")
            )
        return value

    def validate(self, data):
        """Cross-field validation logic, if needed"""
        return data

    def create(self, validated_data):
        return Property.objects.create(**validated_data)

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class PropertyStatsSerializer(serializers.ModelSerializer):
    vacancy_rate = serializers.ReadOnlyField()

    class Meta:
        model = Property
        fields = [
            'id', 'name', 'vacancy_rate', 'is_active'
        ]
        read_only_fields = ['id', 'name', 'is_active']


class PropertyBulkUpdateSerializer(serializers.Serializer):
    """Serializer for bulk operations on properties"""
    property_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False,
        help_text=_("List of property IDs to update")
    )
    is_active = serializers.BooleanField(
        required=False,
        help_text=_("Set active status for selected properties")
    )
    manager = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.filter(role='property_manager'),
        required=False,
        help_text=_("Assign manager to selected properties")
    )
    office = serializers.PrimaryKeyRelatedField(
        queryset=Office.objects.all(),
        required=False,
        help_text=_("Assign office to selected properties")
    )

    def validate_property_ids(self, value):
        """Validate that all property IDs exist"""
        existing_ids = set(
            Property.objects.filter(id__in=value).values_list('id', flat=True)
        )
        provided_ids = set(value)

        if not provided_ids.issubset(existing_ids):
            missing_ids = provided_ids - existing_ids
            raise serializers.ValidationError(
                f"Properties with IDs {list(missing_ids)} do not exist."
            )
        return value

    def validate(self, data):
        """Ensure at least one field to update is provided"""
        update_fields = ['is_active', 'manager', 'office']
        if not any(field in data for field in update_fields):
            raise serializers.ValidationError(
                _("At least one field to update must be provided.")
            )
        return data
class AssignPropertyManagerSerializer(serializers.Serializer):
    property_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False,
        help_text=_("List of property IDs")
    )
    manager = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.filter(role='property_manager'),
        help_text=_("Property manager to assign")
    )

    def validate_property_ids(self, value):
        existing_ids = set(
            Property.objects.filter(id__in=value).values_list('id', flat=True)
        )
        missing_ids = set(value) - existing_ids

        if missing_ids:
            raise serializers.ValidationError(
                _(f"Properties with IDs {list(missing_ids)} do not exist.")
            )
        return value
    

class UnitListSerializer(serializers.ModelSerializer):
    """Serializer for listing units with minimal data"""
    property_name = serializers.CharField(
        source='property.name', read_only=True)
    unit_type_display = serializers.CharField(
        source='get_unit_type_display', read_only=True)

    class Meta:
        model = Unit
        fields = [
            'id', 'name', 'abbreviated_name', 'property_name', 'unit_type',
            'unit_type_display', 'monthly_rent', 'occupied_status', 'created_at'
        ]


class UnitDetailSerializer(serializers.ModelSerializer):
    """Serializer for detailed unit information"""
    property_name = serializers.CharField(
        source='property.name', read_only=True)
    unit_type_display = serializers.CharField(
        source='get_unit_type_display', read_only=True)

    class Meta:
        model = Unit
        fields = [
            'id', 'property', 'property_name', 'name', 'abbreviated_name',
            'unit_number', 'unit_type', 'unit_type_display', 'description',
            'monthly_rent', 'deposit_amount', 'occupied_status',
            'created_at', 'updated_at'
        ]


class UnitCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating units"""

    class Meta:
        model = Unit
        fields = [
            'property', 'name', 'abbreviated_name', 'unit_number', 'unit_type',
            'description', 'monthly_rent', 'deposit_amount', 'occupied_status'
        ]

    def validate_monthly_rent(self, value):
        if value < 0:
            raise serializers.ValidationError(
                _("Monthly rent cannot be negative.")
            )
        return value

    def validate_deposit_amount(self, value):
        if value < 0:
            raise serializers.ValidationError(
                _("Deposit amount cannot be negative.")
            )
        return value

    def validate(self, attrs):
        # Check if unit_number is unique within the property
        property_obj = attrs.get('property')
        unit_number = attrs.get('unit_number')

        if property_obj and unit_number:
            queryset = Unit.objects.filter(
                property=property_obj, unit_number=unit_number)
            if self.instance:
                queryset = queryset.exclude(pk=self.instance.pk)

            if queryset.exists():
                raise serializers.ValidationError({
                    'unit_number': _('Unit with this unit number already exists for this property.')
                })

        return attrs
