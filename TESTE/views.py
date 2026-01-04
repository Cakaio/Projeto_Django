from django.contrib.auth import authenticate, login
from django.shortcuts import render, redirect
from django.views.generic import TemplateView


class inicio(TemplateView):
    template_name = "inicio.html"
