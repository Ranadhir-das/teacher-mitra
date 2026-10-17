from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        user = self.model(email=self.normalize_email(email).lower(), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("role", "SUPER_ADMIN")
        if not all(extra_fields.get(field) for field in ("is_staff", "is_superuser", "is_active")):
            raise ValueError("Superuser must be active, staff and superuser")
        if extra_fields["role"] != "SUPER_ADMIN":
            raise ValueError("Superuser must have SUPER_ADMIN role")
        return self.create_user(email, password, **extra_fields)
