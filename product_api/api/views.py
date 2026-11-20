from django.http import HttpResponse
from rest_framework import viewsets
from .messaging import publish_event
from .models import Product
from .serializers import ProductSerializer


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

    def get_queryset(self):
        queryset = Product.objects.all()
        group_id = self.request.query_params.get('group_id') or self.request.query_params.get('group')
        if self.action == 'list' and not group_id:
            return queryset.none()
        barcode = self.request.query_params.get('barcode')
        category = self.request.query_params.get('category')
        status_param = self.request.query_params.get('status')
        if group_id:
            queryset = queryset.filter(group_id=str(group_id))
        if barcode:
            queryset = queryset.filter(barcode=barcode)
        if category:
            queryset = queryset.filter(category=category)
        if status_param:
            queryset = queryset.filter(status=status_param)
        return queryset

    def perform_create(self, serializer):
        added_by = serializer.validated_data.get('added_by')
        user_id = getattr(self.request.user, 'id', None)
        if not added_by:
            added_by = str(user_id) if user_id is not None else ''
        instance = serializer.save(added_by=added_by)
        publish_event(
            'activity.product_created',
            {
                'group_id': str(instance.group_id),
                'user_id': str(user_id) if user_id is not None else added_by,
                'entity_type': 'product',
                'entity_id': str(instance.id),
                'description': f'Produto "{instance.name}" cadastrado',
            },
        )


def health_check(request):
    return HttpResponse('OK', status=200)
