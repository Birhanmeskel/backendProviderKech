"""Structured auth audit logging (no passwords, minimal PII)."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger("kech.auth")


def mask_phone(phone: str | None) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) <= 4:
        return "***"
    return f"***{digits[-4:]}"


def log_token_success(phone: str | None) -> None:
    logger.info("auth.token.success", extra={"masked_phone": mask_phone(phone)})


def log_token_failure(phone: str | None, status_code: int) -> None:
    logger.warning(
        "auth.token.failure",
        extra={"masked_phone": mask_phone(phone), "status_code": status_code},
    )


def log_logout(user_id: int | None) -> None:
    logger.info("auth.logout", extra={"user_id": user_id})


def log_account_deleted(*, user_id: int, role: str) -> None:
    logger.info(
        "auth.account.deleted",
        extra={"user_id": user_id, "role": role, "action": "deactivated"},
    )


def log_register_success(user_id: int, role: str) -> None:
    logger.info("auth.register.success", extra={"user_id": user_id, "role": role})


def log_register_failure(phone: str | None, status_code: int) -> None:
    logger.warning(
        "auth.register.failure",
        extra={"masked_phone": mask_phone(phone), "status_code": status_code},
    )


def log_sales_agent_create(actor_user_id: int | None, created_user_id: int, phone: str | None) -> None:
    logger.info(
        "auth.sales_agent.create",
        extra={
            "actor_user_id": actor_user_id,
            "created_user_id": created_user_id,
            "masked_phone": mask_phone(phone),
        },
    )


def log_driver_approved(*, admin_id: int, driver_user_id: int) -> None:
    logger.info(
        "driver.approved",
        extra={"admin_id": admin_id, "driver_user_id": driver_user_id, "action": "approved"},
    )


def log_driver_rejected(*, admin_id: int, driver_user_id: int) -> None:
    logger.info(
        "driver.rejected",
        extra={"admin_id": admin_id, "driver_user_id": driver_user_id, "action": "rejected"},
    )


def log_driver_suspended(*, admin_id: int, driver_user_id: int) -> None:
    logger.info(
        "driver.suspended",
        extra={"admin_id": admin_id, "driver_user_id": driver_user_id, "action": "suspended"},
    )


def log_driver_reactivated(*, admin_id: int, driver_user_id: int) -> None:
    logger.info(
        "driver.reactivated",
        extra={"admin_id": admin_id, "driver_user_id": driver_user_id, "action": "reactivated"},
    )
