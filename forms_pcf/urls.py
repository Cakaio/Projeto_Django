from django.urls import path
from . import views

app_name = 'forms_pcf'

urlpatterns = [
    path('feedback/', views.EnviarFeedbackView.as_view(), name='feedback'),
    path('feedback/sucesso/', views.FeedbackSucessoView.as_view(), name='feedback_sucesso'),
    path('feedback/inbox/', views.FeedbackInboxView.as_view(), name='feedback_inbox'),
]
