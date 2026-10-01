"""安全费用台账业务规则。

口径与台账的所有计算都收口在本模块：
- 应提金额 = 计提基数 × 现行「已发布」口径版本中对应项目类别的提取比例；
- 项目+年度的已提/已用/余额只有一份计算逻辑（_balance），台账页与使用登记共用；
- 提取登记与使用登记分表存放，重复登记（同一项目年度 / 同一张发票）只认第一次；
- 口径调整后通过重填生成新版提取记录，旧记录打上「历史」标记，按当时比例原样保留。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

T_OFFICERS = "sf_officers"
T_PROJECTS = "sf_projects"
T_VERSIONS = "sf_rate_versions"
T_RATES = "sf_rates"
T_ACCRUALS = "sf_accruals"
T_USAGES = "sf_usages"

# 安全费用使用方向（登记使用时的费用类别口径）
EXPENSE_CATEGORIES = [
    "安全防护用品",
    "安全培训教育",
    "应急救援器材",
    "隐患整改支出",
    "安全评价与检测",
    "其他安全支出",
]


def _money(value: float) -> float:
    """金额统一保留两位小数，避免浮点尾巴参与余额比较。"""
    return round(float(value) + 1e-9, 2)


class SafetyFundService:
    # ---------- 基础表访问 ----------
    def _rows(self, table: str) -> list[dict[str, Any]]:
        return store.rows(table)

    def _next_id(self, table: str) -> int:
        return max((int(row.get("id", 0)) for row in self._rows(table)), default=0) + 1

    def _find_project(self, project_no: str) -> dict[str, Any] | None:
        for row in self._rows(T_PROJECTS):
            if row.get("项目编号") == project_no:
                return row
        return None

    def _find_officer(self, officer_no: str) -> dict[str, Any] | None:
        for row in self._rows(T_OFFICERS):
            if row.get("工号") == officer_no:
                return row
        return None

    def _find_version(self, code: str) -> dict[str, Any] | None:
        for row in self._rows(T_VERSIONS):
            if row.get("版本编号") == code:
                return row
        return None

    def _published_versions(self) -> list[dict[str, Any]]:
        versions = [row for row in self._rows(T_VERSIONS) if row.get("状态") == "已发布"]
        return sorted(versions, key=lambda row: int(row.get("生效年度", 0)))

    def _current_version(self) -> dict[str, Any] | None:
        """现行口径：已发布版本里生效年度最新的一版。草稿版本不参与任何计算。"""
        versions = self._published_versions()
        return versions[-1] if versions else None

    def _rates_of(self, version_code: str) -> list[dict[str, Any]]:
        return [row for row in self._rows(T_RATES) if row.get("版本编号") == version_code]

    def _rate(self, version_code: str, category: str) -> float | None:
        for row in self._rates_of(version_code):
            if row.get("项目类别") == category:
                return float(row["提取比例"])
        return None

    # ---------- 唯一一份余额口径 ----------
    def _accrued(self, project_no: str, year: int) -> float:
        """已提金额：只统计现行（非历史）提取记录；历史记录按当时口径留存，不进余额。"""
        return _money(sum(
            float(row.get("应提金额", 0))
            for row in self._rows(T_ACCRUALS)
            if row.get("项目编号") == project_no
            and int(row.get("年度", 0)) == year
            and not row.get("历史")
        ))

    def _used(self, project_no: str, year: int) -> float:
        return _money(sum(
            float(row.get("金额", 0))
            for row in self._rows(T_USAGES)
            if row.get("项目编号") == project_no and int(row.get("年度", 0)) == year
        ))

    def _balance(self, project_no: str, year: int) -> dict[str, float]:
        """项目年度余额的唯一计算入口：台账页和使用登记落账校验取的都是这一份。"""
        accrued = self._accrued(project_no, year)
        used = self._used(project_no, year)
        return {"已提金额": accrued, "已用金额": used, "可用余额": _money(accrued - used)}

    def _find_invoice(self, invoice_no: str) -> dict[str, Any] | None:
        for row in self._rows(T_USAGES):
            if row.get("发票号") == invoice_no:
                return row
        return None

    def _check_officer(
        self, officer_no: str, project: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str | None]:
        """使用登记的身份校验：必须是名册内、本项目、同单位的安全员，否则当场驳回。"""
        officer = self._find_officer(officer_no)
        if officer is None:
            return None, f"登记人工号「{officer_no}」不在安全员名册内，非本项目人员提交当场驳回"
        if project.get("项目编号") not in (officer.get("负责项目") or []):
            return None, (
                f"{officer['姓名']}（{officer['单位']}）不是项目「{project['项目编号']}」的安全员，"
                "只有本项目安全员能登记使用，当场驳回"
            )
        if officer.get("单位") != project.get("所属单位"):
            return None, (
                f"提交人单位「{officer['单位']}」与项目所属单位「{project['所属单位']}」不一致，"
                "跨单位提交当场驳回"
            )
        return officer, None

    # ---------- 页面初始化数据 ----------
    def meta(self) -> dict[str, Any]:
        current = self._current_version()
        return {
            "projects": self._rows(T_PROJECTS),
            "officers": self._rows(T_OFFICERS),
            "expense_categories": EXPENSE_CATEGORIES,
            "current_version": current["版本编号"] if current else None,
            "current_rates": self._rates_of(current["版本编号"]) if current else [],
        }

    # ---------- 口径版本 ----------
    def list_versions(self) -> list[dict[str, Any]]:
        versions = [dict(row) for row in self._rows(T_VERSIONS)]
        for version in versions:
            rates = self._rates_of(str(version["版本编号"]))
            version["提取比例明细"] = [
                {"项目类别": row["项目类别"], "提取比例": float(row["提取比例"])} for row in rates
            ]
            version["是否现行"] = bool(
                version["状态"] == "已发布"
                and self._current_version()
                and self._current_version()["版本编号"] == version["版本编号"]
            )
        versions.sort(key=lambda row: int(row.get("生效年度", 0)), reverse=True)
        return versions

    def create_version(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        code = str(values.get("版本编号") or "").strip()
        name = str(values.get("版本名称") or "").strip()
        year_raw = values.get("生效年度")
        rates = values.get("rates") or values.get("提取比例明细")
        if not code:
            return None, "缺少必填字段：版本编号"
        if self._find_version(code) is not None:
            return None, f"口径版本编号「{code}」已存在，新版本请使用新编号"
        try:
            year = int(year_raw)
        except (TypeError, ValueError):
            return None, "生效年度必须是整数年份，例如 2026"
        if not isinstance(rates, list) or not rates:
            return None, "新版口径至少要登记一条「项目类别 + 提取比例」"

        cleaned: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in rates:
            category = str((item or {}).get("项目类别") or "").strip()
            rate_raw = (item or {}).get("提取比例")
            if not category:
                return None, "比例明细缺少项目类别"
            if category in seen:
                return None, f"项目类别「{category}」在同一版口径里重复了"
            try:
                rate = float(rate_raw)
            except (TypeError, ValueError):
                return None, f"类别「{category}」的提取比例必须是数字（0~1 之间，如 0.025）"
            if not 0 < rate < 1:
                return None, f"类别「{category}」的提取比例 {rate} 非法，必须在 0 与 1 之间"
            seen.add(category)
            cleaned.append({"项目类别": category, "提取比例": rate})

        version = {
            "id": self._next_id(T_VERSIONS),
            "版本编号": code,
            "版本名称": name or f"安全生产费用口径{year}版",
            "生效年度": year,
            "发布日期": "",
            "状态": "草稿",
            "发布说明": str(values.get("发布说明") or "").strip(),
        }
        self._rows(T_VERSIONS).append(version)
        for item in cleaned:
            self._rows(T_RATES).append({
                "id": self._next_id(T_RATES),
                "版本编号": code,
                "项目类别": item["项目类别"],
                "提取比例": item["提取比例"],
            })
        return version, f"口径版本「{code}」已存为草稿，发布后才会作为提取依据"

    def publish_version(self, version_id: int) -> tuple[dict[str, Any] | None, str]:
        version = store.find(T_VERSIONS, version_id)
        if version is None:
            return None, f"口径版本 {version_id} 不存在"
        if version.get("状态") != "草稿":
            return None, f"口径版本「{version['版本编号']}」已是{version.get('状态')}状态，不能重复发布"
        if not self._rates_of(str(version["版本编号"])):
            return None, f"口径版本「{version['版本编号']}」没有任何提取比例，不能发布"
        version["状态"] = "已发布"
        version["发布日期"] = date.today().isoformat()
        return version, f"口径版本「{version['版本编号']}」已发布，成为现行提取口径；请对存量执行「按新版重填」"

    # ---------- 提取登记 ----------
    def list_accruals(
        self,
        *,
        project_no: str | None = None,
        year: int | None = None,
        history: bool = False,
    ) -> list[dict[str, Any]]:
        rows = [dict(row) for row in self._rows(T_ACCRUALS) if bool(row.get("历史")) == history]
        if project_no:
            rows = [row for row in rows if row.get("项目编号") == project_no]
        if year is not None:
            rows = [row for row in rows if int(row.get("年度", 0)) == year]
        projects = {row["项目编号"]: row for row in self._rows(T_PROJECTS)}
        for row in rows:
            project = projects.get(row.get("项目编号"), {})
            row["项目名称"] = project.get("项目名称", "")
            row["所属单位"] = project.get("所属单位", "")
            row["项目类别"] = project.get("项目类别", "")
        rows.sort(key=lambda row: (int(row.get("年度", 0)), str(row.get("项目编号"))), reverse=True)
        return rows

    def create_accrual(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        project_no = str(values.get("项目编号") or "").strip()
        officer_no = str(values.get("登记人工号") or "").strip()
        year_raw = values.get("年度")
        base_raw = values.get("计提基数")

        project = self._find_project(project_no)
        if project is None:
            return None, f"项目编号「{project_no}」不存在，无法计算应提金额"
        try:
            year = int(year_raw)
        except (TypeError, ValueError):
            return None, "年度必须是整数，例如 2025"
        try:
            base = float(base_raw)
        except (TypeError, ValueError):
            return None, "计提基数必须是金额数字"
        if base <= 0:
            return None, "计提基数必须大于 0"

        officer, message = self._check_officer(officer_no, project)
        if officer is None:
            return None, message or "登记人校验未通过"

        # 同一项目同一年度只认第一次提取登记
        for row in self._rows(T_ACCRUALS):
            if (
                row.get("项目编号") == project_no
                and int(row.get("年度", 0)) == year
                and not row.get("历史")
            ):
                return None, (
                    f"项目「{project_no}」{year} 年度提取已于 {row.get('登记日期')} "
                    f"按口径 {row.get('口径版本')} 登记（流水 {row.get('id')}，应提 "
                    f"{_money(float(row['应提金额'])):.2f}），同一笔费用只认第一次，本次重复登记驳回"
                )

        version = self._current_version()
        if version is None:
            return None, "当前没有任何已发布的提取口径，无法计算应提金额"
        rate = self._rate(str(version["版本编号"]), str(project.get("项目类别")))
        if rate is None:
            return None, (
                f"现行口径「{version['版本编号']}」中没有项目类别「{project.get('项目类别')}」"
                "的提取比例，应提金额无法计算，请先补充口径"
            )

        amount = _money(base * rate)
        entry = {
            "id": self._next_id(T_ACCRUALS),
            "项目编号": project_no,
            "年度": year,
            "口径版本": version["版本编号"],
            "计提基数": _money(base),
            "提取比例": rate,
            "应提金额": amount,
            "登记日期": date.today().isoformat(),
            "登记人工号": officer_no,
            "历史": False,
            "备注": str(values.get("备注") or "").strip(),
        }
        self._rows(T_ACCRUALS).append(entry)
        return entry, (
            f"提取已登记：{project_no} {year} 年度按现行口径 {version['版本编号']} "
            f"（比例 {rate * 100:g}%）应提 {amount:.2f} 元"
        )

    def refill(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """口径调整后的存量重填：旧版现行记录转历史（比例原样保留），按新版重建一份。"""
        version = self._current_version()
        if version is None:
            return None, "当前没有已发布口径，无法重填"
        year_raw = values.get("年度")
        year = None
        if year_raw not in (None, ""):
            try:
                year = int(year_raw)
            except (TypeError, ValueError):
                return None, "年度必须是整数，例如 2025"

        currents = [
            row for row in self._rows(T_ACCRUALS)
            if not row.get("历史") and (year is None or int(row.get("年度", 0)) == year)
        ]
        if not currents:
            return None, "没有找到需要重填的现行提取记录"

        # 先整表校验：新版缺任何一个项目类别的比例，整批不落地，避免重填到一半
        for row in currents:
            project = self._find_project(str(row.get("项目编号")))
            category = str(project.get("项目类别")) if project else ""
            if self._rate(str(version["版本编号"]), category) is None:
                return None, (
                    f"现行口径「{version['版本编号']}」缺少类别「{category}」的提取比例，"
                    f"项目「{row.get('项目编号')}」无法重填，本次重填整批作废"
                )

        today = date.today().isoformat()
        created: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for old in currents:
            project = self._find_project(str(old["项目编号"]))
            rate = self._rate(str(version["版本编号"]), str(project["项目类别"]))
            if old.get("口径版本") == version["版本编号"]:
                skipped.append({"流水": old["id"], "项目编号": old["项目编号"],
                                "年度": old["年度"], "原因": "已是现行口径，无需重填"})
                continue
            new_amount = _money(float(old["计提基数"]) * float(rate))
            old["历史"] = True
            old["备注"] = (
                f"{today} 口径调整为 {version['版本编号']}，本记录转历史，"
                f"按当时口径 {old.get('口径版本')} 的比例原样保留"
            )
            entry = {
                "id": self._next_id(T_ACCRUALS),
                "项目编号": old["项目编号"],
                "年度": int(old["年度"]),
                "口径版本": version["版本编号"],
                "计提基数": _money(float(old["计提基数"])),
                "提取比例": float(rate),
                "应提金额": new_amount,
                "登记日期": today,
                "登记人工号": str(values.get("登记人工号") or old.get("登记人工号") or ""),
                "历史": False,
                "备注": f"按新版口径 {version['版本编号']} 重填",
            }
            self._rows(T_ACCRUALS).append(entry)
            created.append(entry)

        if not created:
            summary = {"重填笔数": 0, "新增明细": [], "跳过": skipped,
                       "现行口径": version["版本编号"]}
            return summary, "所选记录均已按现行口径登记，没有需要重填的内容"
        summary = {"重填笔数": len(created), "新增明细": created, "跳过": skipped,
                   "现行口径": version["版本编号"]}
        return summary, (
            f"已按新版口径 {version['版本编号']} 重填 {len(created)} 条；"
            "旧记录按当时比例保留在历史台账"
        )

    # ---------- 使用登记 ----------
    def list_usages(
        self,
        *,
        project_no: str | None = None,
        year: int | None = None,
        keyword: str | None = None,
    ) -> dict[str, Any]:
        rows = [dict(row) for row in self._rows(T_USAGES)]
        if project_no:
            rows = [row for row in rows if row.get("项目编号") == project_no]
        if year is not None:
            rows = [row for row in rows if int(row.get("年度", 0)) == year]
        if keyword:
            rows = [
                row for row in rows
                if keyword in str(row.get("发票号", "")) or keyword in str(row.get("用途说明", ""))
            ]
        rows.sort(key=lambda row: int(row.get("id", 0)), reverse=True)

        # 合计随每一笔登记实时重算，从不落库，保证和单笔流水同源
        category_total: dict[str, float] = {}
        for row in rows:
            category_total[row["费用类别"]] = _money(
                category_total.get(row["费用类别"], 0.0) + float(row["金额"])
            )
        return {
            "items": rows,
            "total": len(rows),
            "合计金额": _money(sum(category_total.values())),
            "按类别合计": [
                {"费用类别": category, "金额": amount}
                for category, amount in sorted(category_total.items())
            ],
        }

    def create_usage(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        project_no = str(values.get("项目编号") or "").strip()
        officer_no = str(values.get("登记人工号") or "").strip()
        category = str(values.get("费用类别") or "").strip()
        invoice_no = str(values.get("发票号") or "").strip()
        purpose = str(values.get("用途说明") or "").strip()
        year_raw = values.get("年度")
        amount_raw = values.get("金额")

        project = self._find_project(project_no)
        if project is None:
            return None, f"项目编号「{project_no}」不存在，使用登记当场驳回"

        # 身份先查：跨单位 / 非本项目安全员当场驳回
        officer, message = self._check_officer(officer_no, project)
        if officer is None:
            return None, message or "登记人校验未通过"

        try:
            year = int(year_raw)
        except (TypeError, ValueError):
            return None, "年度必须是整数，例如 2025"
        try:
            amount = _money(float(amount_raw))
        except (TypeError, ValueError):
            return None, "使用金额必须是数字"
        if amount <= 0:
            return None, "使用金额必须大于 0"
        if not category:
            return None, "缺少必填字段：费用类别"
        if not invoice_no:
            return None, "缺少必填字段：发票号"
        if not purpose:
            return None, "缺少必填字段：用途说明"

        # 同一张发票全库只生效一次（不分项目、不分年度）
        existed = self._find_invoice(invoice_no)
        if existed is not None:
            return None, (
                f"发票号「{invoice_no}」已在流水 {existed.get('id')}（{existed.get('登记日期')}，"
                f"项目 {existed.get('项目编号')}，金额 {_money(float(existed['金额'])):.2f}）报销过，"
                "同一张发票重复报销只生效第一次，本次不予落账"
            )

        # 余额校验：与项目台账页取同一份 _balance
        balance = self._balance(project_no, year)
        if balance["已提金额"] <= 0:
            return None, (
                f"项目「{project_no}」{year} 年度尚无提取登记，已提余额 0.00 元，"
                f"本次申请 {amount:.2f} 元全部超出，不许落账"
            )
        if amount > balance["可用余额"]:
            over = _money(amount - balance["可用余额"])
            return None, (
                f"超出已提余额，不许落账：{project_no} {year} 年度已提 "
                f"{balance['已提金额']:.2f}、已使用 {balance['已用金额']:.2f}、可用余额 "
                f"{balance['可用余额']:.2f}，本次申请 {amount:.2f}，超出 {over:.2f} 元"
            )

        entry = {
            "id": self._next_id(T_USAGES),
            "项目编号": project_no,
            "年度": year,
            "费用类别": category,
            "金额": amount,
            "发票号": invoice_no,
            "用途说明": purpose,
            "登记日期": date.today().isoformat(),
            "登记人工号": officer["工号"],
            "登记人姓名": officer["姓名"],
            "登记人单位": officer["单位"],
        }
        self._rows(T_USAGES).append(entry)
        return entry, (
            f"使用登记已落账：{amount:.2f} 元（{category}），"
            f"落账后余额 {_money(balance['可用余额'] - amount):.2f} 元"
        )

    # ---------- 项目台账 ----------
    def ledger(
        self, *, project_no: str | None = None, year: int | None = None
    ) -> dict[str, Any]:
        """项目年度台账：每个项目年度一行，已提/已用/余额实时汇总，与登记校验同源。"""
        accruals = [
            row for row in self._rows(T_ACCRUALS)
            if not row.get("历史")
            and (not project_no or row.get("项目编号") == project_no)
            and (year is None or int(row.get("年度", 0)) == year)
        ]
        items: list[dict[str, Any]] = []
        for row in accruals:
            project = self._find_project(str(row["项目编号"])) or {}
            pno = str(row["项目编号"])
            yr = int(row["年度"])
            balance = self._balance(pno, yr)
            items.append({
                "项目编号": pno,
                "项目名称": project.get("项目名称", ""),
                "所属单位": project.get("所属单位", ""),
                "项目类别": project.get("项目类别", ""),
                "年度": yr,
                "口径版本": row.get("口径版本"),
                "计提基数": _money(float(row["计提基数"])),
                "提取比例": float(row["提取比例"]),
                "应提金额": balance["已提金额"],
                "已用金额": balance["已用金额"],
                "可用余额": balance["可用余额"],
                "最近提取日期": row.get("登记日期"),
            })
        items.sort(key=lambda row: (row["年度"], row["项目编号"]), reverse=True)
        return {
            "items": items,
            "total": len(items),
            "合计": {
                "应提金额": _money(sum(row["应提金额"] for row in items)),
                "已用金额": _money(sum(row["已用金额"] for row in items)),
                "可用余额": _money(sum(row["可用余额"] for row in items)),
            },
        }
