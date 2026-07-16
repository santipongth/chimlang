"""Read-only active product and governance policy."""

from fastapi import APIRouter, Depends

from api.auth import get_principal
from core.product_policy import active_product_policy
from governance.rbac import Principal

router = APIRouter(tags=["policy"])


@router.get("/product-policy.json")
def product_policy_json(
    principal: Principal = Depends(get_principal),
) -> dict:
    return active_product_policy()
