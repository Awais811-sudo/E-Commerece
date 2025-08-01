from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import get_user_model
from .models import Address
from django import forms
from .models import Product, Address
User = get_user_model()

from django import forms
from .models import Address

class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        exclude = ['user', 'slug', 'is_default', 'created_at']
        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Full Name',
                'required': 'required'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Email Address',
                'required': 'required'
            }),           
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Phone Number',
                'required': 'required'
            }),
            'street': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Street Address',
                'required': 'required'
            }),
            'city': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'City',
                'required': 'required'
            }),
            'state': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'State/Province',
                'required': 'required'
            }),
            'postal_code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Postal/Zip Code',
                'required': 'required'
            }),
            'country': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Country',
                'required': 'required'
            }),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # If user is authenticated and has email, pre-fill email and make readonly
        if user and user.is_authenticated and user.email:
            self.fields['email'].initial = user.email
            self.fields['email'].widget.attrs['readonly'] = True
            
            # Try to pre-fill name from user profile if available
            if hasattr(user, 'get_full_name') and user.get_full_name():
                self.fields['full_name'].initial = user.get_full_name()
            elif user.first_name or user.last_name:
                self.fields['full_name'].initial = f"{user.first_name} {user.last_name}".strip()



class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            'name', 'slug', 'description', 'price', 'discount_price',
            'category', 'tags', 'stock', 'available', 'featured', 
            'sold', 'weight', 'views', 'view_count', 'last_sold',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def clean_price(self):
        price = self.cleaned_data.get('price')
        if price <= 0:
            raise forms.ValidationError("Price must be greater than zero.")
        return price

    def clean_stock(self):
        stock = self.cleaned_data.get('stock')
        if stock < 0:
            raise forms.ValidationError("Stock cannot be negative.")
        return stock





class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        # Adjust these fields as needed; the default User model includes 'username', 'email', etc.
        fields = ('username', 'email', 'password1', 'password2')

class CustomAuthenticationForm(AuthenticationForm):
    username = forms.CharField(label='Username')

class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = ['street', 'city', 'state', 'postal_code', 'country', 'is_default']
