"""安全费用台账接口。

- 项目台账 /api/safetyfund/ledger：已提、已用、余额与使用登记落账校验取同一份计算结果；
- 提取登记 /api/safetyfund/accruals：应提金额只按现行「已发布」口径版本计算；
- 使用登记 /api/safetyfund/usages：与提取分开，重复发票、超余额、非本项目安全员一律驳回；
- 口径版本 /api/safetyfund/versions：新版先存草稿，发布后通过重填更新存量，历史记录保留。
"""
from __future__ import annotations

from fastapi import APIRouter

from app.schemas import (
    AccrualPayload,
    ActionResult,
    RateVersionPayload,
    RefillPayload,
    UsagePayload,
)
from app.services.safetyfund import SafetyFundService

router = APIRouter(prefix="/api/safetyfund", tags=["安全费用台账"])

service = SafetyFundService()


@router.get("/meta")
def meta() -> dict[str, object]:
    """表单初始化：项目、安全员名册、费用类别与现行口径比例。"""
    return service.meta()


@router.get("/ledger")
def ledger(
    项目编号: str | None = None,
    年度: int | None = None,
) -> dict[str, object]:
    """项目年度台账：应提、已用、可用余额实时汇总，所有页面取的都是这同一份。"""
    return service.ledger(project_no=项目编号, year=年度)


@router.get("/accruals")
def list_accruals(
    项目编号: str | None = None,
    年度: int | None = None,
    历史: bool = False,
) -> dict[str, object]:
    """提取登记明细；历史=true 时只看按旧口径保留下来的历史台账。"""
    items = service.list_accruals(project_no=项目编号, year=年度, history=历史)
    return {"items": items, "total": len(items), "历史": 历史}


@router.post("/accruals", response_model=ActionResult)
def create_accrual(payload: AccrualPayload) -> ActionResult:
    """登记一笔年度提取；应提金额由现行口径自动计算，重复登记同一项目年度只认第一次。"""
    entry, message = service.create_accrual(payload.model_dump())
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/accruals/refill", response_model=ActionResult)
def refill_accruals(payload: RefillPayload) -> ActionResult:
    """口径调整后按新版重填存量提取；旧版记录转历史，按当时比例原样保留。"""
    summary, message = service.refill(payload.model_dump())
    if summary is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=summary)


@router.get("/usages")
def list_usages(
    项目编号: str | None = None,
    年度: int | None = None,
    关键字: str | None = None,
) -> dict[str, object]:
    """使用明细：合计与按类别合计随每一笔登记实时重算，不单独落库。"""
    return service.list_usages(project_no=项目编号, year=年度, keyword=关键字)


@router.post("/usages", response_model=ActionResult)
def create_usage(payload: UsagePayload) -> ActionResult:
    """登记一笔安全费用使用；超余额、发票重复、非本项目安全员或跨单位提交均当场驳回。"""
    entry, message = service.create_usage(payload.model_dump())
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/versions")
def list_versions() -> dict[str, object]:
    """口径版本清单：草稿、已发布与现行标记一目了然。"""
    items = service.list_versions()
    return {"items": items, "total": len(items)}


@router.post("/versions", response_model=ActionResult)
def create_version(payload: RateVersionPayload) -> ActionResult:
    """新建一版提取口径，存为草稿；草稿不参与任何应提金额计算。"""
    entry, message = service.create_version(payload.model_dump())
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/versions/{version_id}/publish", response_model=ActionResult)
def publish_version(version_id: int) -> ActionResult:
    """发布草稿口径，使其成为现行提取依据。"""
    entry, message = service.publish_version(version_id)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
