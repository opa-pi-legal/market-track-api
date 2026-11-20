from django.core.management.base import BaseCommand
from api.models import Product

GLOBAL_CATALOG_SEED = [
    ('7896006711117', 'Arroz Branco Tipo 1 5kg', 'Camil', 'Mercearia', 'pct', 1),
    ('7896006744115', 'Feijão Carioca Tipo 1 1kg', 'Camil', 'Mercearia', 'pct', 1),
    ('7896089011357', 'Café Tradicional 500g', 'Pilão', 'Bebidas', 'pct', 1),
    ('7898215151784', 'Leite Integral UHT 1L', 'Piracanjuba', 'Laticínios', 'un', 1),
    ('7896036090244', 'Óleo de Soja 900ml', 'Liza', 'Mercearia', 'un', 1),
    ('5601031001012', 'Azeite Extra Virgem 500ml', 'Gallo', 'Mercearia', 'un', 1),
    ('7891910000197', 'Açúcar Refinado 1kg', 'União', 'Mercearia', 'pct', 1),
    ('7896005200278', 'Macarrão Espaguete 500g', 'Adria', 'Mercearia', 'pct', 1),
    ('7896004000015', 'Molho de Tomate Tradicional 300g', 'Heinz', 'Mercearia', 'un', 1),
    ('7891000100103', 'Leite Condensado 395g', 'Moça', 'Laticínios', 'un', 1),
    ('7891000315507', 'Creme de Leite 200g', 'Nestlé', 'Laticínios', 'un', 1),
    ('7891098000156', 'Manteiga com Sal 200g', 'Aviação', 'Laticínios', 'un', 1),
    ('7893000394209', 'Margarina com Sal 500g', 'Qualy', 'Laticínios', 'un', 1),
    ('7894900011517', 'Refrigerante Cola 2L', 'Coca-Cola', 'Bebidas', 'un', 1),
    ('7891991010856', 'Cerveja Pilsen Lata 350ml', 'Brahma', 'Bebidas', 'un', 1),
    ('7896098900208', 'Detergente Líquido Neutro 500ml', 'Ypê', 'Limpeza', 'un', 1),
    ('7891150039810', 'Sabão em Pó Lavagem Perfeita 1,6kg', 'OMO', 'Limpeza', 'cx', 1),
    ('7896098901182', 'Amaciante Concentrado 1L', 'Ypê', 'Limpeza', 'un', 1),
    ('7896015513146', 'Água Sanitária 2L', 'Qboa', 'Limpeza', 'un', 1),
    ('7896018701014', 'Papel Higiênico Folha Dupla 12 rolos', 'Neve', 'Higiene', 'pct', 1),
    ('7891024131107', 'Creme Dental Total 12 90g', 'Colgate', 'Higiene', 'un', 1),
    ('7891150026421', 'Sabonete em Barra 90g', 'Dove', 'Higiene', 'un', 1),
    ('7896005800027', 'Sal Refinado 1kg', 'Cisne', 'Mercearia', 'pct', 1),
    ('7896005201022', 'Farinha de Trigo 1kg', 'Dona Benta', 'Mercearia', 'pct', 1),
    ('7891000053508', 'Achocolatado em Pó 400g', 'Nescau', 'Bebidas', 'un', 1),
]


class Command(BaseCommand):
    help = 'Popula o catálogo global curado de produtos básicos (idempotente).'

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0
        for ean, name, brand, category, unit, qty in GLOBAL_CATALOG_SEED:
            _, created = Product.objects.update_or_create(
                group_id='global',
                barcode=ean,
                defaults={
                    'name': name,
                    'brand': brand,
                    'category': category,
                    'unit': unit,
                    'quantity': qty,
                    'status': 'active',
                    'is_global': True,
                    'verified_source': 'seed',
                    'added_by': 'system',
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Catálogo global pronto: {created_count} criados, {updated_count} atualizados.'
            )
        )
