"""安全费用台账业务规则。

口径要点：
- 应提金额 = 项目年度计提基数 × 已发布口径版本的提取比例；比例只能取自发布版本，不能手填。
- 提取登记按「项目 + 年度 + 口径版本」幂等，重复登记只认第一次。
- 使用登记与提取登记分开；使用前校验已提余额，超额当场驳回并说明超额多少。
- 同一发票号全局唯一，重复报销只生效一次；只有本项目安全员（姓名与所属单位同时匹配）
  能登记使用，跨单位提交当场驳回。
- 口径版本发布后，从生效年度起重算存量年度的应提（重填一版），历史年度按当时比例保留：
  台账永远取「生效年度不晚于该年度的最新版本」对应的那一版提取登记。
- 台账的已提/已用/余额与使用登记页取同一份聚合结果，不做任何双份缓存。
"""
from __future__ import annotations

from typing import Any

from app.store import store

PROJECT = "safetyfee_project"
BASE = "safetyfee_base"
POLICY = "safetyfee_policy"
ACCRUAL = "safetyfee_accrual"
USAGE = "safetyfee_usage"

_PENDING_FIELDS = {"status", "pending", "abnormal"}


def _to_amount(value: Any, field: str) -> tuple[float | None, str | None]:
    """金额/基数入参校验：必须是不小于 0 的数。"""
    if value is None or str(value).strip() == "":
        return None, f"{field}不能为空"
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None, f"{field}必须是数字"
    if amount < 0:
        return None, f"{field}不能为负"
    return round(amount, 2), None


def _next_id(rows: list[dict[str, Any]]) -> int:
    return max((int(row.get("id", 0)) for row in rows), default=0) + 1


class SafetyFeeService:
    # ------------------------------------------------------------------ 项目
    def list_projects(self) -> list[dict[str, Any]]:
        return store.rows(PROJECT)

    def get_project(self, project_id: int) -> dict[str, Any] | None:
        return store.find(PROJECT, project_id)

    # ---------------------------------------------------------------- 口径版本
    def list_policies(self) -> list[dict[str, Any]]:
        return store.rows(POLICY)

    def publish_policy(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """发布一版提取口径，并从生效年度起重算存量年度的应提。"""
        name = str(values.get("版本名称") or "").strip()
        note = str(values.get("说明") or "").strip()
        rate, rate_err = _to_amount(values.get("提取比例"), "提取比例")
        if not name:
            return None, "口径版本名称不能为空"
        if rate_err:
            return None, rate_err
        if not 0 < rate < 100:
            return None, "提取比例必须在 0~100（不含边界）之间，单位为百分数"
        try:
            effective_year = int(values.get("生效年度"))
        except (TypeError, ValueError):
            return None, "生效年度必须是 4 位年份整数"

        policies = store.rows(POLICY)
        for row in policies:
            if int(row["生效年度"]) == effective_year:
                return None, f"{effective_year} 年度已发布过口径「{row['版本名称']}」，同一年度不能重复发布"

        policy = {
            "id": _next_id(policies),
            "版本名称": name,
            "提取比例": rate,
            "生效年度": effective_year,
            "发布日期": str(values.get("发布日期") or "").strip() or None,
            "说明": note or None,
        }
        policies.append(policy)
        self._refill_for_policy(policy)
        return policy, f"口径「{name}」已发布，已按 {rate:g}% 重填 {effective_year} 年度起的存量应提"

    def policy_for_year(self, year: int) -> dict[str, Any] | None:
        """某年度适用的口径：生效年度不晚于该年度的最新版本。"""
        candidates = [row for row in store.rows(POLICY) if int(row["生效年度"]) <= year]
        if not candidates:
            return None
        return max(candidates, key=lambda row: (int(row["生效年度"]), int(row["id"])))

    def _refill_for_policy(self, policy: dict[str, Any]) -> list[dict[str, Any]]:
        """新口径发布后，对生效年度起、已维护基数的存量年度重填一版提取登记。

        历史登记不删不改（历史台账仍按当时版本取数），重算结果作为新版本的一版落库。
        """
        accruals = store.rows(ACCRUAL)
        refilled: list[dict[str, Any]] = []
        for base_row in store.rows(BASE):
            year = int(base_row["年度"])
            if year < int(policy["生效年度"]):
                continue
            if self._find_accrual(base_row["项目ID"], year, int(policy["id"])) is not None:
                continue
            amount = round(float(base_row["年度基数"]) * float(policy["提取比例"]) / 100, 2)
            entry = {
                "id": _next_id(accruals),
                "项目ID": base_row["项目ID"],
                "年度": year,
                "口径版本ID": policy["id"],
                "版本名称": policy["版本名称"],
                "提取比例": policy["提取比例"],
                "应提金额": amount,
                "计提基数": float(base_row["年度基数"]),
                "登记日期": policy.get("发布日期"),
                "来源": "口径重填",
            }
            accruals.append(entry)
            refilled.append(entry)
        return refilled

    # ---------------------------------------------------------------- 年度基数
    def list_bases(self, project_id: int | None = None) -> list[dict[str, Any]]:
        rows = store.rows(BASE)
        if project_id is not None:
            rows = [row for row in rows if int(row["项目ID"]) == project_id]
        return rows

    def upsert_base(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """维护项目某年度的计提基数；该年度已有适用口径时同步重算应提。"""
        project_id, year = self._parse_project_year(values)
        if project_id is None:
            return None, str(year)
        if self.get_project(project_id) is None:
            return None, f"项目 {project_id} 不存在"
        base_amount, err = _to_amount(values.get("年度基数"), "年度基数")
        if err:
            return None, err

        rows = store.rows(BASE)
        row = next((item for item in rows
                    if int(item["项目ID"]) == project_id and int(item["年度"]) == year), None)
        if row is None:
            row = {"id": _next_id(rows), "项目ID": project_id, "年度": year}
            rows.append(row)
        row["年度基数"] = base_amount

        policy = self.policy_for_year(year)
        message = f"{year} 年度计提基数已保存为 {base_amount:,.2f}"
        if policy is not None:
            self._ensure_accrual(project_id, year, policy, base=base_amount, source="基数维护")
            message += f"，已按现行口径「{policy['版本名称']}」{policy['提取比例']:g}% 重算应提"
        else:
            message += "；该年度尚无适用口径，应提暂不计算"
        return row, message

    def _parse_project_year(self, values: dict[str, Any]) -> tuple[int | None, Any]:
        try:
            project_id = int(values.get("项目ID"))
        except (TypeError, ValueError):
            return None, "项目ID必须是整数"
        try:
            year = int(values.get("年度"))
        except (TypeError, ValueError):
            return None, "年度必须是 4 位年份整数"
        if year < 1900 or year > 9999:
            return None, "年度必须是 4 位年份整数"
        return project_id, year

    # ---------------------------------------------------------------- 提取登记
    def list_accruals(self, project_id: int | None = None, year: int | None = None) -> list[dict[str, Any]]:
        rows = store.rows(ACCRUAL)
        if project_id is not None:
            rows = [row for row in rows if int(row["项目ID"]) == project_id]
        if year is not None:
            rows = [row for row in rows if int(row["年度"]) == year]
        return rows

    def _find_accrual(self, project_id: int, year: int, policy_id: int) -> dict[str, Any] | None:
        for row in store.rows(ACCRUAL):
            if (int(row["项目ID"]) == project_id and int(row["年度"]) == year
                    and int(row["口径版本ID"]) == policy_id):
                return row
        return None

    def _ensure_accrual(
        self,
        project_id: int,
        year: int,
        policy: dict[str, Any],
        *,
        base: float | None = None,
        source: str = "提取登记",
    ) -> tuple[dict[str, Any], bool]:
        """按现行口径确保一版提取登记存在；返回 (登记, 是否新建)。"""
        existing = self._find_accrual(project_id, year, int(policy["id"]))
        if existing is not None:
            return existing, False
        if base is None:
            base_row = next(
                (row for row in store.rows(BASE)
                 if int(row["项目ID"]) == project_id and int(row["年度"]) == year),
                None,
            )
            if base_row is None:
                raise ValueError("尚未维护该年度的计提基数，无法计算应提")
            base = float(base_row["年度基数"])
        accruals = store.rows(ACCRUAL)
        entry = {
            "id": _next_id(accruals),
            "项目ID": project_id,
            "年度": year,
            "口径版本ID": policy["id"],
            "版本名称": policy["版本名称"],
            "提取比例": policy["提取比例"],
            "计提基数": round(base, 2),
            "应提金额": round(base * float(policy["提取比例"]) / 100, 2),
            "登记日期": None,
            "来源": source,
        }
        accruals.append(entry)
        return entry, True

    def register_accrual(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str, bool]:
        """提取登记：比例只能按发布口径走；同一项目同一年度同一口径只认第一次。"""
        project_id, year = self._parse_project_year(values)
        if project_id is None:
            return None, str(year), False
        project = self.get_project(project_id)
        if project is None:
            return None, f"项目 {project_id} 不存在", False
        policy = self.policy_for_year(year)
        if policy is None:
            return None, f"{year} 年度尚无已发布的提取口径，不能登记提取", False
        try:
            entry, created = self._ensure_accrual(project_id, year, policy)
        except ValueError as exc:
            return None, str(exc), False
        if created:
            entry["登记日期"] = str(values.get("登记日期") or "").strip() or entry["登记日期"]
            return entry, (
                f"{project['项目名称']} {year} 年度已按「{policy['版本名称']}」"
                f"{policy['提取比例']:g}% 提取 {entry['应提金额']:,.2f} 元"
            ), True
        return entry, (
            f"{project['项目名称']} {year} 年度在口径「{policy['版本名称']}」下的提取已登记过"
            f"（{entry['应提金额']:,.2f} 元），重复登记只认第一次"
        ), False

    # ---------------------------------------------------------------- 使用登记
    def list_usages(
        self,
        *,
        project_id: int | None = None,
        year: int | None = None,
        invoice_no: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = store.rows(USAGE)
        if project_id is not None:
            rows = [row for row in rows if int(row["项目ID"]) == project_id]
        if year is not None:
            rows = [row for row in rows if int(row["年度"]) == year]
        if invoice_no:
            rows = [row for row in rows if invoice_no in str(row.get("发票号码", ""))]
        return rows

    def _sum_usages(self, project_id: int, year: int) -> float:
        return round(sum(
            float(row["使用金额"]) for row in store.rows(USAGE)
            if int(row["项目ID"]) == project_id and int(row["年度"]) == year
        ), 2)

    def register_usage(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """使用登记：身份、发票唯一性、余额三道闸口，任一不过当场驳回。"""
        project_id, year = self._parse_project_year(values)
        if project_id is None:
            return None, str(year)
        project = self.get_project(project_id)
        if project is None:
            return None, f"项目 {project_id} 不存在"

        operator = str(values.get("登记人") or "").strip()
        operator_unit = str(values.get("登记人单位") or "").strip()
        if not operator or not operator_unit:
            return None, "登记人姓名与所属单位都必须填写"
        # 先查跨单位，再查是不是本项目安全员，顺序与驳回口径保持一致。
        if operator_unit != str(project.get("所属单位")):
            return None, (
                f"跨单位提交当场驳回：{operator_unit} 不属于项目"
                f"「{project['项目名称']}」的所属单位（{project['所属单位']}）"
            )
        if operator != str(project.get("安全员")):
            return None, (
                f"只有本项目安全员（{project['安全员']}）能登记使用，"
                f"{operator} 不是该项目安全员"
            )

        invoice_no = str(values.get("发票号码") or "").strip()
        if not invoice_no:
            return None, "发票号码不能为空"
        duplicate = next(
            (row for row in store.rows(USAGE) if str(row.get("发票号码")) == invoice_no),
            None,
        )
        if duplicate is not None:
            return None, (
                f"发票 {invoice_no} 已在 {duplicate['年度']} 年度报销过"
                f"（{duplicate['使用金额']:,.2f} 元），同一张发票只生效一次"
            )

        amount, err = _to_amount(values.get("使用金额"), "使用金额")
        if err:
            return None, err
        if amount == 0:
            return None, "使用金额必须大于 0"

        ledger = self.ledger_entry(project_id, year)
        if ledger is None or float(ledger["已提金额"]) == 0.0:
            return None, f"{project['项目名称']} {year} 年度尚未提取安全费用，无余额可用"
        balance = float(ledger["余额"])
        if amount > balance:
            over = round(amount - balance, 2)
            return None, (
                f"超出已提余额，不许落账：本次使用 {amount:,.2f} 元，"
                f"当前余额仅 {balance:,.2f} 元，超出 {over:,.2f} 元"
            )

        rows = store.rows(USAGE)
        entry = {
            "id": _next_id(rows),
            "项目ID": project_id,
            "年度": year,
            "项目名称": project["项目名称"],
            "使用金额": amount,
            "用途": str(values.get("用途") or "").strip() or None,
            "发票号码": invoice_no,
            "登记人": operator,
            "登记人单位": operator_unit,
            "登记日期": str(values.get("登记日期") or "").strip() or None,
        }
        rows.append(entry)
        return entry, (
            f"使用登记成功：{amount:,.2f} 元已落账，"
            f"{project['项目名称']} {year} 年度剩余余额 {round(balance - amount, 2):,.2f} 元"
        )

    # ---------------------------------------------------------------- 台账
    def ledger_entry(self, project_id: int, year: int) -> dict[str, Any] | None:
        """单个项目年度台账。已提/已用/余额全部现场聚合，页面各处共用这一份。"""
        project = self.get_project(project_id)
        if project is None:
            return None
        policy = self.policy_for_year(year)
        accrual: dict[str, Any] | None = None
        if policy is not None:
            accrual = self._find_accrual(project_id, year, int(policy["id"]))
        accrued = float(accrual["应提金额"]) if accrual else 0.0
        used = self._sum_usages(project_id, year)
        return {
            "项目ID": project_id,
            "项目名称": project["项目名称"],
            "所属单位": project["所属单位"],
            "安全员": project["安全员"],
            "年度": year,
            "适用版本": policy["版本名称"] if policy else None,
            "提取比例": policy["提取比例"] if policy else None,
            "已提金额": accrued,
            "已用金额": used,
            "余额": round(accrued - used, 2),
        }

    def ledger(self, *, project_id: int | None = None, year: int | None = None) -> list[dict[str, Any]]:
        """项目 × 年度台账：基数表决定有哪些年度格子，逐格取同一份聚合。"""
        keys = sorted(
            {
                (int(row["项目ID"]), int(row["年度"]))
                for row in store.rows(BASE)
                if project_id is None or int(row["项目ID"]) == project_id
            },
            key=lambda item: (item[0], item[1]),
        )
        entries = [self.ledger_entry(pid, yr) for pid, yr in keys]
        if year is not None:
            entries = [row for row in entries if row is not None and int(row["年度"]) == year]
        return [row for row in entries if row is not None]

    def usage_summary(
        self,
        *,
        project_id: int | None = None,
        year: int | None = None,
    ) -> dict[str, Any]:
        """使用明细汇总：合计随每一笔登记现场重算，不做存量合计。"""
        rows = self.list_usages(project_id=project_id, year=year)
        total = round(sum(float(row["使用金额"]) for row in rows), 2)
        return {"笔数": len(rows), "合计金额": total}
