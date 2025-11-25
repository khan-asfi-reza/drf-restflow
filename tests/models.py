from django.db import models


class SampleModel(models.Model):
    """Sample model for filter tests"""

    integer_field = models.IntegerField(null=True, blank=True)
    string_field = models.CharField(max_length=255, null=True, blank=True)
    boolean_field = models.BooleanField(default=False)
    date_field = models.DateField(null=True, blank=True)
    datetime_field = models.DateTimeField(null=True, blank=True)
    decimal_field = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    email_field = models.EmailField(null=True, blank=True)
    choice_field = models.CharField(
        max_length=10,
        choices=[("a", "Option A"), ("b", "Option B"), ("c", "Option C")],
        null=True,
        blank=True,
    )

    class Meta:
        app_label = "tests"


class SampleAbstractModel(models.Model):
    """Sample abstract model for filter tests"""

    char_field = models.CharField(max_length=255)

    class Meta:
        abstract = True


class RelatedModel(models.Model):
    """Related model for testing foreign keys"""

    sample_model = models.ForeignKey(
        SampleModel, on_delete=models.CASCADE, related_name="related_items"
    )
    name = models.CharField(max_length=100)

    class Meta:
        app_label = "tests"
