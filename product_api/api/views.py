from django.db.models import Q
from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from .messaging import publish_event
from .models import Product
from .serializers import ProductSerializer


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

    def _is_staff_request(self) -> bool:
        return bool(
            getattr(self.request.user, 'is_staff', False)
            or (self.request.auth and self.request.auth.get('is_staff'))
        )

    def get_queryset(self):
        queryset = Product.objects.all()
        group_id = self.request.query_params.get('group_id') or self.request.query_params.get('group')
        include_global = self.request.query_params.get('include_global', 'false').lower() in ('true', '1', 'yes')
        global_only = self.request.query_params.get('global_only', 'false').lower() in ('true', '1', 'yes')
        all_groups = self.request.query_params.get('all_groups', 'false').lower() in ('true', '1', 'yes')

        if self.action == 'list':
            if all_groups and self._is_staff_request():
                pass
            elif global_only:
                queryset = queryset.filter(is_global=True)
            elif group_id and include_global:
                queryset = queryset.filter(Q(group_id=str(group_id)) | Q(is_global=True))
            elif group_id:
                queryset = queryset.filter(group_id=str(group_id))
            else:
                return queryset.none()
        elif group_id:
            queryset = queryset.filter(Q(group_id=str(group_id)) | Q(is_global=True))

        barcode = self.request.query_params.get('barcode')
        category = self.request.query_params.get('category')
        status_param = self.request.query_params.get('status')
        q = (self.request.query_params.get('q') or '').strip()
        if barcode:
            queryset = queryset.filter(barcode=barcode)
        if category:
            queryset = queryset.filter(category=category)
        if status_param:
            queryset = queryset.filter(status=status_param)
        if q:
            queryset = queryset.filter(
                Q(name__icontains=q) | Q(brand__icontains=q) | Q(barcode__icontains=q)
            )
        return queryset.order_by('-is_global', 'name')

    def perform_create(self, serializer):
        added_by = serializer.validated_data.get('added_by')
        user_id = getattr(self.request.user, 'id', None)
        if not added_by:
            added_by = str(user_id) if user_id is not None else ''
        instance = serializer.save(added_by=added_by, is_global=False, verified_source='group')
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

    @action(detail=True, methods=['post'], url_path='promote-global')
    def promote_global(self, request, pk=None):
        is_staff = bool(
            getattr(request.user, 'is_staff', False)
            or (request.auth and request.auth.get('is_staff'))
        )
        if not is_staff:
            return Response(
                {'detail': 'Apenas moderadores podem promover produtos ao catálogo global.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        product = self.get_object()
        source = (request.data.get('verified_source') or 'admin').strip().lower()
        if source not in ('seed', 'openfoodfacts', 'admin'):
            source = 'admin'
        product.is_global = True
        product.verified_source = source
        product.save(update_fields=['is_global', 'verified_source', 'last_updated'])
        return Response(self.get_serializer(product).data, status=status.HTTP_200_OK)


def health_check(request):
    return HttpResponse('OK', status=200)
