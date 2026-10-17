from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from ..models import User


class LoginSerializer(TokenObtainPairSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = False
        self.fields["username"] = serializers.CharField(required=False, write_only=True)

    def validate(self, attrs):
        identifier = attrs.get("email") or attrs.get("username")
        if not identifier:
            raise serializers.ValidationError("Email or username is required.")
        if attrs.get("email") and attrs.get("username"):
            raise serializers.ValidationError("Supply either email or username, not both.")
        attrs.pop("username", None)
        attrs["email"] = identifier.strip().lower()
        result = super().validate(attrs)
        if self.user.role == User.Role.PARTNER:
            from apps.partners.models import Partner
            from apps.partners.permissions import LOGIN_STATUSES
            if not Partner.objects.filter(user=self.user, status__in=LOGIN_STATUSES).exists():
                from rest_framework.exceptions import AuthenticationFailed
                raise AuthenticationFailed("Your partner account is awaiting approval or is inactive.")
        return result


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "name", "email", "phone", "profile_photo", "role", "is_active", "date_joined", "last_login")
        read_only_fields = fields


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()
