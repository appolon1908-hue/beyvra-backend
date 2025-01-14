from django.utils import translation

class UserPreferredLanguageMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            preferred_language = request.user.preferred_language
            translation.activate(preferred_language)
        else:
            translation.deactivate()
        response = self.get_response(request)
        return response
