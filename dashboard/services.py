from django.db.models import Sum
from django.db.models.functions import TruncMonth
from shop.models import Order

def get_sales_chart():
    data = Order.objects.annotate(
        month=TruncMonth('created_at')
    ).values('month').annotate(
        total=Sum('total_price')
    ).order_by('month')
    
    return {
        'labels': [item['month'].strftime("%b %Y") for item in data],
        'datasets': [{
            'label': 'Sales',
            'data': [float(item['total']) for item in data]
        }]
    }