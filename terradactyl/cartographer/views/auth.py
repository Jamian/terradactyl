from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout

from django.shortcuts import redirect, render
from django.views import View



class LoginView(View):
    def get(self, request):
        return render(request, 'login.html', {})

    def post(self, request):
        email = request.POST['email']
        password = request.POST['password']
        user = authenticate(request, username=email, password=password)
        if user is not None:
            auth_login(request, user)
            return redirect('index')

class LogoutView(View):
    def get(self, request):
        auth_logout(request)
        return redirect('login')
