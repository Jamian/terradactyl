from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout

from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods


@require_http_methods(['GET', 'POST'])
def login(request):
    """View for login.
    """
    if request.method == 'POST':
        email = request.POST['email']
        password = request.POST['password']
        user = authenticate(request, username=email, password=password)
        if user is not None:
            auth_login(request, user)
            return redirect('index')
        else:
            return render(request, 'login.html', {})
    else:
        return render(request, 'login.html', {})


@require_http_methods(['GET'])
def logout(request):
    """View for logout
    """
    auth_logout(request)
    return redirect('login')
