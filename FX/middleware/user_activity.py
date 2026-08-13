import json
import logging

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.http import HttpRequest
from django.urls import resolve, reverse
from django.utils.deprecation import MiddlewareMixin
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from middleware.log_activity import log
from security.models import UserActivityActionTypes
from security.utils import get_logged_user
from users.models import UserRoles

logger = logging.getLogger(__name__)
User = get_user_model()


LOGIN_USER_URL = reverse("user:token_obtain_pair")
TOKEN_LOGOUT_USER_URL = reverse("user:token_logout")
CREATE_USER_URL = reverse("user:create")
DELETE_USER_URL = reverse("user:delete")
DISABLE_WALKTHROUGH_USER_URL = reverse("user:disable_walkthrough")
ENABLE_MFA_USER_URL = reverse("user:enable_mfa")
SET_TWO_FACTOR_USER_URL = reverse("user:set_two_factor")
FORGOT_PASSWORD_USER_URL = reverse("user:password_reset")
PASSWORD_CHANGE_USER_URL = reverse("user:password_change")
ADMIN_SET_GLOBAL_2FA_USER_URL = reverse("admin_set_global_two_factor")

preset_actions = [
    LOGIN_USER_URL,
    TOKEN_LOGOUT_USER_URL,
    CREATE_USER_URL,
    DELETE_USER_URL,
    DISABLE_WALKTHROUGH_USER_URL,
    ENABLE_MFA_USER_URL,
    SET_TWO_FACTOR_USER_URL,
    FORGOT_PASSWORD_USER_URL,
    PASSWORD_CHANGE_USER_URL,
    ADMIN_SET_GLOBAL_2FA_USER_URL,
]


def check_login_activity(request: HttpRequest, user):
    """
    Check login attempts. This allows logging for login attempts
    even if the authentication backend raises an exception (e.g., incorrect password).
    """
    if request.path == LOGIN_USER_URL and request.method == "POST":
        if user:
            return user
        else:
            return False


def check_logout_activity(request: HttpRequest):
    """Check logout attempts"""
    if request.path == TOKEN_LOGOUT_USER_URL and request.method == "POST":
        user: User = get_logged_user(request)
        if user:
            return user
        else:
            return False


def check_signup_activity(request: HttpRequest, user):
    """
    Check signup attempts. This allows logging for signup attempts
    even if the authentication backend raises an exception
    (e.g., user already exists)."""
    if request.path == CREATE_USER_URL and request.method == "POST":
        if user:
            return user
        else:
            return False


def check_delete_activity(request: HttpRequest):
    """Check delete user attempts."""
    if request.path == DELETE_USER_URL and request.method == "DELETE":
        user: User = get_logged_user(request)
        if user:
            return user
        else:
            return False


def check_user_update_activity(request: HttpRequest):
    """Check user update attempts."""
    if request.path == ENABLE_MFA_USER_URL and request.method == "GET":
        user: User = get_logged_user(request)
        if user:
            return {"user": user, "info": "Enable MFA", "status": True}
        else:
            return {"user": None, "info": "Enable MFA", "status": False}
    elif request.path == SET_TWO_FACTOR_USER_URL and request.method == "PATCH":
        user: User = get_logged_user(request)
        if user:
            return {"user": user, "info": "Set 2FA", "status": True}
        else:
            return {"user": None, "info": "Set 2FA", "status": False}


def check_user_forgot_password_activity(request: HttpRequest):
    """Check user forgot password attempts."""
    if request.path == FORGOT_PASSWORD_USER_URL and request.method == "POST":
        user: User = get_logged_user(request)
        if user:
            return user
        else:
            return False


def check_user_password_reset(request: HttpRequest):
    """Check user password reset attempts."""
    match = resolve(request.path)
    if match.url_name == "password_reset_confirm" and request.method == "POST":
        uidb64 = match.kwargs.get("uidb64")
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user: User = User.objects.get(pk=uid)
            if user:
                return user
            else:
                return False
        except Exception as e:
            logger.warning(e)

        return False


def check_user_password_change(request: HttpRequest):
    """Check user password change attempts."""
    if request.path == PASSWORD_CHANGE_USER_URL and request.method == "POST":
        user: User = get_logged_user(request)
        if user:
            return user
        else:
            return False


def check_admin_global_set_2fa_activity(request: HttpRequest):
    """Check when admin sets 2fa for global users attempts."""
    if request.path == ADMIN_SET_GLOBAL_2FA_USER_URL and request.method == "PATCH":
        user: User = get_logged_user(request)
        if user:
            return user
        else:
            return False


def check_admin_activities(request: HttpRequest):
    """Check all admin activities attempts, except for those in predefined actions since they are already captured"""
    user = request.user
    if user:
        is_admin = User.objects.filter(
            Q(role__iexact=UserRoles.Admin.value) | Q(role__iexact=UserRoles.Super_Admin.value)
        ).first()
        if is_admin and request.path not in preset_actions:
            # get path name if available
            path_name = resolve(request.path).url_name
            action = f"{UserActivityActionTypes.OTHER_ADMIN_ACTION.value}_{(path_name if path_name else request.path)}"

            return {"user": user, "action": action}


class UserActivitiesMiddleware(MiddlewareMixin):
    user_email = None
    login_user = None
    logout_user = None
    signup_user = None
    delete_user = None
    update_user = None
    forgot_password_user = None
    password_reset_user = None
    password_change_user = None
    admin_user = None
    other_admin_actions = None

    def process_view(self, request, view_func, view_args, view_kwargs):
        try:
            # If content type is JSON, try to parse it
            if request.content_type == "application/json":
                data = json.loads(request.body.decode("utf-8"))
            else:
                data = request.POST
            self.user_email = data.get("email")
        except Exception as e:
            logger.warning("Error parsing request data in middleware")

        user = User.objects.filter(email__iexact=self.user_email).first()

        # CAPTURE LOGIN
        self.login_user: User | bool = check_login_activity(request, user)

        # CAPTURE LOGOUT
        self.logout_user: User | bool = check_logout_activity(request)

        # CAPTURE SIGNUP
        self.signup_user: User | bool = check_signup_activity(request, user)

        # CAPTURE DELETE
        self.delete_user: User | bool = check_delete_activity(request)

        # CAPTURE UPDATE
        self.update_user: User | bool = check_user_update_activity(request)

        # CAPTURE FORGOT PASSWORD
        self.forgot_password_user: User | bool = check_user_forgot_password_activity(request)

        # CAPTURE PASSWORD RESET
        self.password_reset_user: User | bool = check_user_password_reset(request)

        # CAPTURE PASSWORD CHANGE
        self.password_change_user: User | bool = check_user_password_change(request)

        # CAPTURE ADMIN SET GLOBAL USER 2FA
        self.admin_user: User | bool = check_admin_global_set_2fa_activity(request)

        # CAPTURE ALL OTHER ADMIN ACTIONS
        self.other_admin_actions: dict | bool = check_admin_activities(request)

        return None

    def process_response(self, request, response):
        status_code = response.status_code
        # log logged-in user
        if self.login_user or self.login_user is False:
            self._log_action(
                request=request,
                action_type=UserActivityActionTypes.LOGIN.value,
                user=self.login_user,
                identifier=self.login_user,
                status_code=status_code,
            )

        # log logged-out user
        if self.logout_user or self.logout_user is False:
            self._log_action(
                request=request,
                action_type=UserActivityActionTypes.LOGOUT.value,
                user=self.logout_user if isinstance(self.logout_user, User) else None,
                identifier=self.logout_user if isinstance(self.logout_user, User) else self.logout_user,
                status_code=status_code,
            )

        # log user signup
        if isinstance(self.signup_user, User) or self.signup_user is False:
            self._log_action(
                request=request,
                action_type=UserActivityActionTypes.CREATE.value,
                user=self.signup_user if isinstance(self.signup_user, User) else None,
                identifier=self.user_email,
                status_code=status_code,
            )

        # log user delete
        if isinstance(self.delete_user, User) or self.delete_user is False:
            self._log_action(
                request=request,
                action_type=UserActivityActionTypes.DELETE.value,
                user=None,
                identifier=self.delete_user.email if isinstance(self.delete_user, User) else self.delete_user,
                status_code=status_code,
            )

        # log user update
        if self.update_user:
            self._log_action(
                request=request,
                action_type=f"{UserActivityActionTypes.UPDATE.value}",
                desc=self.update_user["info"],
                user=self.update_user["user"],
                identifier=self.update_user["user"] if self.update_user["user"] else self.update_user["status"],
                status_code=status_code,
            )

        # log user forgot password
        if self.forgot_password_user or self.forgot_password_user is False:
            self._log_action(
                request=request,
                action_type=UserActivityActionTypes.FORGOT_PASSWORD.value,
                user=self.forgot_password_user if isinstance(self.forgot_password_user, User) else None,
                identifier=self.user_email,
                status_code=status_code,
            )

        # log user password reset
        if self.password_reset_user or self.password_reset_user is False:
            self._log_action(
                request=request,
                action_type=UserActivityActionTypes.PASSWORD_RESET.value,
                user=self.password_reset_user if isinstance(self.password_reset_user, User) else None,
                identifier=(
                    self.password_reset_user.email
                    if isinstance(self.password_reset_user, User)
                    else self.password_reset_user
                ),
                status_code=status_code,
            )

        # log user password change
        if self.password_change_user or self.password_change_user is False:
            self._log_action(
                request=request,
                action_type=UserActivityActionTypes.CHANGE_PASSWORD.value,
                user=self.password_change_user if isinstance(self.password_change_user, User) else None,
                identifier=(
                    self.password_change_user.email
                    if isinstance(self.password_change_user, User)
                    else self.password_change_user
                ),
                status_code=status_code,
            )

        # log admin set 2FA
        if self.admin_user or self.admin_user is False:
            self._log_action(
                request=request,
                action_type=UserActivityActionTypes.ADMIN_GLOBAL_SET_2FA.value,
                user=self.admin_user if isinstance(self.admin_user, User) else None,
                identifier=(self.admin_user.email if isinstance(self.admin_user, User) else self.admin_user),
                status_code=status_code,
            )

        # log other admin actions
        if self.other_admin_actions:
            self._log_action(
                request=request,
                action_type=self.other_admin_actions["action"],
                user=self.other_admin_actions["user"] if isinstance(self.other_admin_actions, dict) else None,
                identifier=self.other_admin_actions["user"].email,
                status_code=status_code,
            )

        return response

    def _log_action(self, request, user, action_type, identifier, status_code=200, desc: str = ""):
        # handle anonymous user
        if identifier is False or identifier is None:
            user = None
            identifier = "Unknown user"
        log(
            request=request,
            action_type=action_type,
            desc=f"{action_type} - {desc}  attempt success -> {identifier}",
            err_msg=f"{action_type} - {desc} attempt failed -> {identifier}",
            user=user,
            status_code=status_code,
        )
