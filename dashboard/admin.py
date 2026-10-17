from django.contrib import admin

from dashboard.models import (
    AnalysisReport,
    Company,
)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "symbol",
        "sector",
        "active",
    )

    search_fields = (
        "name",
        "symbol",
    )


@admin.register(AnalysisReport)
class AnalysisReportAdmin(admin.ModelAdmin):

    list_display = (
        "company_symbol",
        "sentiment",
        "risk_level",
        "signal",
        "created_at",
    )

    list_filter = (
        "sentiment",
        "risk_level",
        "signal",
    )

    search_fields = (
        "company_name",
        "company_symbol",
    )