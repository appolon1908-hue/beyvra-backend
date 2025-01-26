from django.contrib.admin import SimpleListFilter
from security.models import UserActivityActionTypes


class CustomActionTypeFilter(SimpleListFilter):
    title = "Action Type"
    parameter_name = "custom_action_type"

    def lookups(self, request, model_admin):
        # get all predefined action_types except custom base OTHER_ADMIN_ACTION
        predefined_types = [
            choice[1]
            for choice in UserActivityActionTypes.choices()
            if choice[1] != UserActivityActionTypes.OTHER_ADMIN_ACTION.value
        ]

        # Get all unique action types from the database
        action_types = sorted(
            set(
                (
                    model_admin.model.objects.exclude(action_type__in=predefined_types)
                    .values_list("action_type", flat=True)
                    .distinct()
                )
            )
        )

        predefined_and_custom_types = predefined_types + action_types
        all_types = [(action, action) for action in predefined_and_custom_types]
        return all_types

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(action_type=self.value())
        return queryset
