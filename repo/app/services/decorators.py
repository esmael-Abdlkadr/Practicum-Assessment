from functools import wraps

from flask import abort, redirect, request, session, url_for

from app.services import rbac_service
from app.services import session_service


def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        user = session_service.get_current_user()
        if not user:
            return redirect(url_for("auth.login_page"))
        return view_func(*args, **kwargs)

    return wrapper


def high_risk_action(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        action = view_func.__name__
        if not session_service.has_reauth_for(action):
            session_service.require_reauth(action)
            session["reauth_next"] = request.path
            return redirect(url_for("auth.reauth_page", next=request.path))
        return view_func(*args, **kwargs)

    return wrapper


def require_role(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            user = session_service.get_current_user()
            if not user:
                return redirect(url_for("auth.login_page"))
            if session_service.get_active_role() not in roles:
                return abort(403)
            return view_func(*args, **kwargs)

        return wrapper

    return decorator


def require_scope(scope_type, id_param="id"):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            user = session_service.get_current_user()
            if not user:
                return redirect(url_for("auth.login_page"))

            try:
                resource_id = kwargs.get(id_param) or request.view_args.get(id_param)
                target_id = int(resource_id)
            except (TypeError, ValueError):
                return abort(400)

            if scope_type == "cohort":
                if not rbac_service.can_access_cohort(user, target_id, effective_role=session_service.get_active_role()):
                    return abort(403)
            elif scope_type == "student":
                if not rbac_service.can_access_student(user, target_id, effective_role=session_service.get_active_role()):
                    return abort(403)

            return view_func(*args, **kwargs)

        return wrapper

    return decorator


def permission_required(permission_key):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            user = session_service.get_current_user()
            if not user:
                return redirect(url_for("auth.login_page"))
            active_role = session_service.get_active_role()
            if active_role == "dept_admin" or rbac_service.has_permission(
                user, permission_key, effective_role=active_role
            ):
                return view_func(*args, **kwargs)
            return abort(403)

        return wrapper

    return decorator
