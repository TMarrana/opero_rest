import pytest
from django.contrib.auth import get_user_model

from core.models import Restaurant

User = get_user_model()


@pytest.fixture
def restaurant(db):
    return Restaurant.objects.create(name="Tasca do Teste", slug="tasca-do-teste")


def _user(restaurant, email, role):
    return User.objects.create_user(
        email=email, password="segredo-de-teste-123", restaurant=restaurant, role=role
    )


@pytest.fixture
def admin_user(restaurant):
    return _user(restaurant, "admin@tasca.pt", User.Role.ADMIN)


@pytest.fixture
def manager(restaurant):
    return _user(restaurant, "gerente@tasca.pt", User.Role.MANAGER)


@pytest.fixture
def stock_user(restaurant):
    return _user(restaurant, "stock@tasca.pt", User.Role.STOCK)


@pytest.fixture
def staff_user(restaurant):
    return _user(restaurant, "colaborador@tasca.pt", User.Role.STAFF)
