"""测试: schemas/trip.py — Pydantic 模型验证"""

import pytest
from datetime import date
from pydantic import ValidationError
from schemas.trip import (
    TripFormData, TripResult, GenerateResponse, GenerateStatusResponse,
    StyleEnum, BudgetEnum, AccommodationEnum, TripStatusEnum,
    DestinationItem, TripSummary,
)


# =============================================================
# TripFormData
# =============================================================
class TestTripFormData:

    def test_valid_form(self):
        """合法数据应通过验证"""
        form = TripFormData(
            destination="杭州",
            startDate="2025-06-01",
            endDate="2025-06-03",
        )
        assert form.destination == "杭州"
        assert form.adults == 2        # 默认值
        assert form.children == 0      # 默认值

    def test_end_date_before_start_raises(self):
        """结束日期早于开始日期 → ValidationError"""
        with pytest.raises(ValidationError, match="结束日期不能早于开始日期"):
            TripFormData(
                destination="杭州",
                startDate="2025-06-05",
                endDate="2025-06-03",
            )

    def test_days_property(self):
        """days = (end_date - start_date).days + 1"""
        form = TripFormData(
            destination="杭州",
            startDate="2025-06-01",
            endDate="2025-06-03",
        )
        assert form.days == 3  # 1日+2日+3日

    def test_single_day_trip(self):
        """当天往返：days = 1"""
        form = TripFormData(
            destination="杭州",
            startDate="2025-06-01",
            endDate="2025-06-01",
        )
        assert form.days == 1

    def test_nights_property(self):
        """nights = (end_date - start_date).days"""
        form = TripFormData(
            destination="杭州",
            startDate="2025-06-01",
            endDate="2025-06-03",
        )
        assert form.nights == 2

    def test_people_property(self):
        """people = adults + children"""
        form = TripFormData(
            destination="杭州",
            startDate="2025-06-01",
            endDate="2025-06-03",
            adults=2,
            children=1,
        )
        assert form.people == 3

    def test_no_children(self):
        """没有儿童时 people == adults"""
        form = TripFormData(
            destination="杭州",
            startDate="2025-06-01",
            endDate="2025-06-03",
            adults=2,
            children=0,
        )
        assert form.people == 2

    def test_all_enum_defaults(self):
        """枚举字段应有正确的默认值"""
        form = TripFormData(
            destination="杭州",
            startDate="2025-06-01",
            endDate="2025-06-03",
        )
        assert form.style == StyleEnum.leisure
        assert form.budget == BudgetEnum.comfort
        assert form.accommodation == AccommodationEnum.comfort


class TestTripFormDataValidation:

    def test_destination_required(self):
        """destination 是必填字段"""
        with pytest.raises(ValidationError):
            TripFormData(
                startDate="2025-06-01",
                endDate="2025-06-03",
            )

    def test_adults_range(self):
        """adults 范围 1~10"""
        with pytest.raises(ValidationError):
            TripFormData(
                destination="杭州",
                startDate="2025-06-01",
                endDate="2025-06-03",
                adults=0,
            )

    def test_children_range(self):
        """children 范围 0~5"""
        with pytest.raises(ValidationError):
            TripFormData(
                destination="杭州",
                startDate="2025-06-01",
                endDate="2025-06-03",
                children=6,
            )

    def test_origin_optional(self):
        """origin 可选字段"""
        form = TripFormData(
            destination="杭州",
            startDate="2025-06-01",
            endDate="2025-06-03",
        )
        assert form.origin is None

    def test_special_needs_optional(self):
        """special_needs 可选字段"""
        form = TripFormData(
            destination="杭州",
            startDate="2025-06-01",
            endDate="2025-06-03",
        )
        assert form.special_needs is None


# =============================================================
# TripResult
# =============================================================
class TestTripResult:

    def test_minimal_trip_result(self, trip_form_data):
        """最小的 TripResult 应能创建"""
        from datetime import datetime
        from schemas.trip import BudgetCategory, BudgetItem, BudgetPieItem
        result = TripResult(
            id="trip_test123",
            title="杭州3日轻松休闲",
            destination="杭州",
            startDate="2025-06-01",
            endDate="2025-06-03",
            days=3,
            nights=2,
            people=2,
            transport="train",
            style="leisure",
            interests=["food"],
            totalBudget=3000,
            budgetPerPerson=1500,
            budgetLevel="comfort",
            budgetDetail={
                "accommodation": {"total": 1000, "icon": "🏨", "items": []},
                "food": {"total": 800, "icon": "🍜", "items": []},
                "transport": {"total": 600, "icon": "🚌", "items": []},
                "tickets": {"total": 600, "icon": "🎫", "items": []},
            },
            budgetPieData=[
                {"name": "住宿", "value": 1000, "color": "#3B82F6", "percent": 33},
            ],
            dailyPlan=[],
            createdAt=datetime.now(),
        )
        assert result.id == "trip_test123"
        assert result.status == TripStatusEnum.completed


# =============================================================
# 进度/响应 Schema
# =============================================================
class TestGenerateResponse:

    def test_fields(self):
        resp = GenerateResponse(tripId="trip_abc", status="processing")
        assert resp.tripId == "trip_abc"
        assert resp.status == "processing"
        assert resp.message == ""


class TestGenerateStatusResponse:

    def test_minimal(self):
        resp = GenerateStatusResponse(tripId="trip_abc", status="processing")
        assert resp.progress == 0
        assert resp.currentStep == ""

    def test_completed_with_result(self):
        resp = GenerateStatusResponse(
            tripId="trip_abc", status="completed",
            progress=100, currentStep="完成",
            result={"title": "test"},
        )
        assert resp.result == {"title": "test"}


# =============================================================
# 其他 Schema
# =============================================================
class TestDestinationItem:

    def test_full(self):
        d = DestinationItem(
            id="beijing", name="北京",
            tags="历史名城", image="img.jpg",
            description="故宫", basePrice=2200,
        )
        assert d.name == "北京"


class TestTripSummary:

    def test_minimal(self):
        from schemas.trip import TripStatusEnum
        s = TripSummary(
            id="t1", title="test", destination="杭州",
            startDate="2025-06-01", endDate="2025-06-03",
            days=3, people=2, status=TripStatusEnum.completed,
            statusText="已完成", budget=3000,
        )
        assert s.month is None
