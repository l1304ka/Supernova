"""
URL configuration for Supernova project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from school import views as school_views

handler400 = school_views.error_400
handler403 = school_views.error_403
handler404 = school_views.error_404
handler500 = school_views.error_500

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('school.urls')),
    path("admin-panel/", include("administrator.urls")),
    path("accounts/", include("account.urls")),
    # preview error pages in development
    path('error/400/', school_views.error_400),
    path('error/403/', school_views.error_403),
    path('error/404/', school_views.error_404),
    path('error/500/', school_views.error_500),
]
