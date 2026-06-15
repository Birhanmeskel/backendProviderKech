from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone

from apps.users.phone_utils import normalize_phone


class UserManager(BaseUserManager):
    """Custom manager for phone-based authentication users."""

    def create_user(self, phone: str, password: str | None = None, **extra_fields):
        if not phone:
            raise ValueError("Phone is required.")

        user = self.model(phone=normalize_phone(phone), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone: str, password: str | None = None, **extra_fields):
        # Superusers must be staff/admin and active.
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("role", User.Role.ADMIN)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(phone=phone, password=password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Project user model.

    Required task fields:
      - id
      - phone (unique)
      - password (via AbstractBaseUser)
      - role (customer, driver, admin, sales)
      - is_active
      - created_at
    """

    class Role(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        DRIVER = "driver", "Driver"
        ADMIN = "admin", "Admin"
        SALES = "sales", "Sales"

    phone = models.CharField(max_length=20, unique=True)
    recovery_email = models.EmailField(
        max_length=254,
        blank=True,
        default="",
        help_text="Staff recovery email for password reset (admin/sales).",
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CUSTOMER,
    )
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS: list[str] = []

    def __str__(self) -> str:
        return f"{self.phone} ({self.role})"
