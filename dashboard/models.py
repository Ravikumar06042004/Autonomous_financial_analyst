from django.db import models


class Company(models.Model):

    id = models.AutoField(
        primary_key=True
    )

    name = models.CharField(
        max_length=200
    )

    symbol = models.CharField(
        max_length=20
    )

    sector = models.CharField(
        max_length=100,
        null=True,
        blank=True,
    )

    active = models.BooleanField(
        default=True
    )

    class Meta:

        managed = False

        db_table = "companies"

        ordering = [
            "name"
        ]


class AnalysisReport(models.Model):

    id = models.AutoField(
        primary_key=True
    )

    company_symbol = models.CharField(
        max_length=20
    )

    company_name = models.CharField(
        max_length=200
    )

    current_price = models.FloatField(
        null=True
    )

    sentiment = models.CharField(
        max_length=30,
        null=True
    )

    sentiment_score = models.FloatField(
        null=True
    )

    risk_level = models.CharField(
        max_length=30,
        null=True
    )

    signal = models.CharField(
        max_length=20,
        null=True
    )

    summary = models.TextField(
        null=True
    )

    technical_view = models.TextField(
        null=True
    )

    reasoning = models.TextField(
        null=True
    )

    report = models.TextField()

    created_at = models.DateTimeField()

    class Meta:

        managed = False

        db_table = "analysis_reports"

        ordering = [
            "-id"
        ]