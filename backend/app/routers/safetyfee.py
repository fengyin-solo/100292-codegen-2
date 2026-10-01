"""安全费用台账接口。

拆分口径：
- /projects /bases /policies：项目、年度计提基数、提取口径版本维护；
- /accruals：提取登记（与使用分开）；
- /usages：使用登记与明细，/usages/summary 给随单笔登记重算的合计；
- /ledger：项目年度台账，页面与登记校验共用 service.ledger_entry 同一份取数。
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.schemas import ActionResult, EntryPayload
from app.services.safetyfee import SafetyFeeService

router = APIRouter(prefix="/api/safetyfee", tags=["安全费用台账"])

service = SafetyFeeService()


@router.get("/projects")
def list_projects() -> dict[str, object]:
    """项目台账页的项目主数据（含所属单位与安全员，供使用登记鉴权）。"""
    items = service.list_projects()
    return {"total": len(items), "items": items}


@router.get("/policies")
def list_policies() -> dict[str, object]:
    """已发布的提取口径版本，按生效年度倒序，最新的在前。"""
    items = sorted(
        service.list_policies(),
        key=lambda row: (int(row["生效年度"]), int(row["id"])),
        reverse=True,
    )
    return {"total": len(items), "items": items}


@router.post("/policies")
def publish_policy(payload: EntryPayload) -> ActionResult:
    """发布新口径：比例只能从这里进系统；发布后生效年度起的存量应提当场重填。"""
    entry, message = service.publish_policy(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/bases")
def list_bases(project_id: int | None = Query(default=None, alias="项目ID")) -> dict[str, object]:
    """年度计提基数清单。"""
    items = service.list_bases(project_id=project_id)
    return {"total": len(items), "items": items}


@router.post("/bases")
def upsert_base(payload: EntryPayload) -> ActionResult:
    """维护（或更正）项目某年度的计提基数；已有适用口径时同步重算该年度应提。"""
    entry, message = service.upsert_base(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/accruals")
def list_accruals(
    project_id: int | None = Query(default=None, alias="项目ID"),
    year: int | None = Query(default=None, alias="年度"),
) -> dict[str, object]:
    """提取登记明细（含历史口径版本，历史台账取当年适用版本）。"""
    items = service.list_accruals(project_id=project_id, year=year)
    return {"total": len(items), "items": items}


@router.post("/accruals/register")
def register_accrual(payload: EntryPayload) -> ActionResult:
    """按项目与年度登记提取；比例强制取已发布口径，同一项目年度版本重复登记只认第一次。"""
    entry, message, created = service.register_accrual(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=created, message=message, entry=entry)


@router.get("/usages")
def list_usages(
    project_id: int | None = Query(default=None, alias="项目ID"),
    year: int | None = Query(default=None, alias="年度"),
    invoice_no: str | None = Query(default=None, alias="发票号码", description="按发票号码检索"),
) -> dict[str, object]:
    """使用登记明细。"""
    items = service.list_usages(project_id=project_id, year=year, invoice_no=invoice_no)
    return {"total": len(items), "items": items}


@router.get("/usages/summary")
def usage_summary(
    project_id: int | None = Query(default=None, alias="项目ID"),
    year: int | None = Query(default=None, alias="年度"),
) -> dict[str, object]:
    """使用明细汇总：合计与笔数每次都按明细现算。"""
    return service.usage_summary(project_id=project_id, year=year)


@router.post("/usages/register")
def register_usage(payload: EntryPayload) -> ActionResult:
    """使用登记：跨单位/非本项目安全员当场驳回，发票重复只生效一次，超额不落账并说明超多少。"""
    entry, message = service.register_usage(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/ledger")
def ledger(
    project_id: int | None = Query(default=None, alias="项目ID"),
    year: int | None = Query(default=None, alias="年度"),
) -> dict[str, object]:
    """项目 × 年度台账：已提、已用、余额与使用登记页取同一份聚合结果。"""
    items = service.ledger(project_id=project_id, year=year)
    total_accrued = round(sum(float(row["已提金额"]) for row in items), 2)
    total_used = round(sum(float(row["已用金额"]) for row in items), 2)
    return {
        "total": len(items),
        "items": items,
        "合计": {"已提金额": total_accrued, "已用金额": total_used, "余额": round(total_accrued - total_used, 2)},
    }
