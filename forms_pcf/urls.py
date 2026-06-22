from django.urls import path
from . import views

app_name = 'forms_pcf'

urlpatterns = [
    path('feedback/', views.EnviarFeedbackView.as_view(), name='feedback'),
    path('feedback/sucesso/', views.FeedbackSucessoView.as_view(), name='feedback_sucesso'),
    path('feedback/inbox/', views.FeedbackInboxView.as_view(), name='feedback_inbox'),
    path('reembolso/', views.EnviarReembolsoView.as_view(), name='reembolso'),
    path('reembolso/sucesso/', views.ReembolsoSucessoView.as_view(), name='reembolso_sucesso'),
    path('reembolso/inbox/', views.ReembolsoInboxView.as_view(), name='reembolso_inbox'),
    path('reembolso/<int:pk>/aprovar/', views.AprovarReembolsoView.as_view(), name='reembolso_aprovar'),
    path('reembolso/<int:pk>/rejeitar/', views.RejeitarReembolsoView.as_view(), name='reembolso_rejeitar'),
]
