"""Administrator home."""

from django.shortcuts import render

from ..decorators import admin_view


@admin_view
def home(request):
    return render(request, "manage/home.html", {})
