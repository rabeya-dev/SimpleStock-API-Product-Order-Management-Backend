from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, inline_serializer

from .serializers import RegistrationSerializer


class RegisterView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        auth=[],
        request=RegistrationSerializer,
        responses={
            201: inline_serializer(
                name='RegistrationResponse',
                fields={
                    'id': serializers.IntegerField(),
                    'username': serializers.CharField(),
                },
            )
        },
    )
    def post(self, request):
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {'id': user.id, 'username': user.username},
            status=201,
        )


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses=inline_serializer(
            name='CurrentUserResponse',
            fields={
                'id': serializers.IntegerField(),
                'username': serializers.CharField(),
            },
        )
    )
    def get(self, request):
        return Response({'id': request.user.id, 'username': request.user.username})
