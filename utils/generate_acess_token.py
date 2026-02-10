from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from typing import Any

User = get_user_model()

def generate_access_token(user: Any):
    refresh = RefreshToken.for_user(user)

    tokens = {"access": str(refresh.access_token), "refresh": str(refresh)}

    return tokens