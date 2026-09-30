"""Typed, contract-specific MCX quantity facts for isolated Swing admission.

The quotation multiplier converts one quoted price point to rupees.  It is
neither a physical quantity nor a Provider order quantity.  No production
issuer of authenticated conversion facts is installed by this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json


class McxQuantityProofOrigin(StrEnum):
    ISOLATED_FIXTURE = "ISOLATED_FIXTURE"
    AUTHENTICATED_PROVIDER = "AUTHENTICATED_PROVIDER"


@dataclass(frozen=True, slots=True)
class McxTypedQuantity:
    lots: int
    physical_quantity_per_lot: Decimal
    physical_unit: str
    quotation_base_quantity: Decimal
    quotation_unit: str
    rupees_per_price_point_per_lot: Decimal
    provider_order_quantity: int
    provider_order_unit: str
    provider_conversion_identity: str
    proof_origin: McxQuantityProofOrigin

    def __post_init__(self) -> None:
        if (
            type(self.lots) is not int or self.lots <= 0
            or any(type(value) is not Decimal or not value.is_finite() or value <= 0
                   for value in (self.physical_quantity_per_lot,
                                 self.quotation_base_quantity,
                                 self.rupees_per_price_point_per_lot))
            or self.physical_unit != self.quotation_unit
            or self.rupees_per_price_point_per_lot
               != self.physical_quantity_per_lot / self.quotation_base_quantity
            or type(self.provider_order_quantity) is not int
            or self.provider_order_quantity <= 0
            or self.provider_order_unit not in {"LOTS", "BASE_UNITS"}
            or not self.provider_conversion_identity
            or type(self.proof_origin) is not McxQuantityProofOrigin
            or (self.provider_order_unit == "LOTS"
                and self.provider_order_quantity != self.lots)
            or (self.provider_order_unit == "BASE_UNITS"
                and Decimal(self.provider_order_quantity)
                    != self.physical_quantity_per_lot * self.lots)
        ):
            raise ValueError("MCX_TYPED_QUANTITY_INVALID")

    @property
    def physical_quantity(self) -> Decimal:
        return self.physical_quantity_per_lot * self.lots

    @property
    def price_to_rupee_multiplier(self) -> Decimal:
        return self.rupees_per_price_point_per_lot * self.lots

    def notional(self, price: Decimal) -> Decimal:
        return price * self.price_to_rupee_multiplier

    def stop_risk(self, entry: Decimal, stop: Decimal) -> Decimal:
        return abs(entry - stop) * self.price_to_rupee_multiplier

    @property
    def identity_sha256(self) -> str:
        return sha256(json.dumps({
            "lots": self.lots,
            "physical_quantity_per_lot": str(self.physical_quantity_per_lot),
            "physical_unit": self.physical_unit,
            "quotation_base_quantity": str(self.quotation_base_quantity),
            "quotation_unit": self.quotation_unit,
            "rupees_per_price_point_per_lot": str(self.rupees_per_price_point_per_lot),
            "provider_order_quantity": self.provider_order_quantity,
            "provider_order_unit": self.provider_order_unit,
            "provider_conversion_identity": self.provider_conversion_identity,
            "proof_origin": self.proof_origin.value,
        }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def quantity_from_dict(value: dict[str, object]) -> McxTypedQuantity:
    try:
        fields = dict(value)
        for name in ("physical_quantity_per_lot", "quotation_base_quantity",
                     "rupees_per_price_point_per_lot"):
            fields[name] = Decimal(fields[name])
        fields["proof_origin"] = McxQuantityProofOrigin(fields["proof_origin"])
        return McxTypedQuantity(**fields)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("MCX_TYPED_QUANTITY_INVALID") from error
