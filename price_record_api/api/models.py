from django.db import models

class PriceRecord(models.Model):
    group_id = models.CharField(max_length=255)
    product_id = models.CharField(max_length=255)
    market_id = models.CharField(max_length=255)
    price_cents = models.BigIntegerField()
    is_promotion = models.BooleanField(default=False)
    recorded_by = models.CharField(max_length=128) 
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "price_records"  

    def __str__(self):
        return f"Preço: {self.price_cents / 100:.2f} pelo Produto {self.product_id} no Mercado {self.market_id}"
