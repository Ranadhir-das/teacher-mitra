from django.contrib.auth.backends import ModelBackend
from .models import User


class EmailOrUsernameBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        identifier = username or kwargs.get(User.USERNAME_FIELD)
        if not identifier or password is None:
            return None
        lookup = {"email__iexact" if "@" in identifier else "username__iexact": identifier.strip()}
        try:
            user = User.objects.get(**lookup)
        except User.DoesNotExist:
            User().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user

    def user_can_authenticate(self, user):
        return super().user_can_authenticate(user) and (user.role != User.Role.COUNSELLOR or user.account_status == User.Status.ACTIVE)
