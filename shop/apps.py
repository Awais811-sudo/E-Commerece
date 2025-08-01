from django.apps import AppConfig

class YourAppConfig(AppConfig):
    name = 'shop'

    def ready(self):
        import shop.signals