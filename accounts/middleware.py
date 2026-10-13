import threading

_threads_locals = threading.local()

def get_current_user():
    return getattr(_threads_locals, 'user', None)

class AuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _threads_locals.user = request.user

        response = self.get_response(request)

        if hasattr(_threads_locals, 'user'):
            del _threads_locals.user

        return response
