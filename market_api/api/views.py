from django.http import HttpResponse
from rest_framework import viewsets
from .messaging import publish_event
from .models import Market
from .serializers import MarketSerializer


class MarketViewSet(viewsets.ModelViewSet):
    queryset = Market.objects.all()
    serializer_class = MarketSerializer

    def _is_staff_request(self) -> bool:
        return bool(
            getattr(self.request.user, 'is_staff', False)
            or (self.request.auth and self.request.auth.get('is_staff'))
        )

    def get_queryset(self):
        queryset = Market.objects.all()
        group_id = self.request.query_params.get('group_id') or self.request.query_params.get('group')
        all_groups = self.request.query_params.get('all_groups', 'false').lower() in ('true', '1', 'yes')
        if self.action == 'list' and not group_id and not (all_groups and self._is_staff_request()):
            return queryset.none()
        status_param = self.request.query_params.get('status')
        if group_id:
            queryset = queryset.filter(group_id=str(group_id))
        if status_param:
            queryset = queryset.filter(status=status_param)
        return queryset.order_by('-created_at')

    def perform_create(self, serializer):
        added_by = serializer.validated_data.get('added_by')
        user_id = getattr(self.request.user, 'id', None)
        if not added_by:
            added_by = str(user_id) if user_id is not None else ''
        instance = serializer.save(added_by=added_by)
        publish_event(
            'activity.market_created',
            {
                'group_id': str(instance.group_id),
                'user_id': str(user_id) if user_id is not None else added_by,
                'entity_type': 'market',
                'entity_id': str(instance.id),
                'description': f'Mercado "{instance.name}" cadastrado',
            },
        )


def health_check(request):
    return HttpResponse('OK', status=200)
